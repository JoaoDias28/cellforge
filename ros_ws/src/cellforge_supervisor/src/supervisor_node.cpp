#include "cellforge_supervisor/supervisor_node.hpp"

#include <behaviortree_cpp/basic_types.h>
#include <behaviortree_cpp/blackboard.h>
#include <openssl/evp.h>

#include <algorithm>
#include <array>
#include <builtin_interfaces/msg/duration.hpp>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <memory>
#include <optional>
#include <regex>
#include <sstream>
#include <string_view>
#include <utility>

#include "cellforge_supervisor/supervisor_nodes.hpp"
#include "cellforge_supervisor/tree_validation.hpp"

using namespace std::chrono_literals;

namespace cellforge_supervisor {
namespace {

constexpr auto kStateQueueDepth = 10;
constexpr auto kEventQueueDepth = 100;

class ScopeExit {
 public:
  explicit ScopeExit(std::function<void()> callback) : callback_(std::move(callback)) {}
  ~ScopeExit() { callback_(); }

  ScopeExit(const ScopeExit&) = delete;
  auto operator=(const ScopeExit&) -> ScopeExit& = delete;

  void dismiss() {
    callback_ = []() {};
  }

 private:
  std::function<void()> callback_;
};

auto isUuid(const std::string& value) -> bool {
  static const std::regex uuid_pattern(
      R"(^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$)");
  return std::regex_match(value, uuid_pattern);
}

auto isSha256(const std::string& value) -> bool {
  static const std::regex pattern(R"(^[0-9a-f]{64}$)");
  return std::regex_match(value, pattern);
}

auto isGitRevision(const std::string& value) -> bool {
  static const std::regex pattern(R"(^[0-9a-f]{40}$)");
  return std::regex_match(value, pattern);
}

auto sha256(const std::string& value) -> std::string {
  auto context =
      std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1 ||
      EVP_DigestUpdate(context.get(), value.data(), value.size()) != 1) {
    throw std::runtime_error("Could not initialize SHA-256 validation.");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int digest_length = 0;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &digest_length) != 1) {
    throw std::runtime_error("Could not finalize SHA-256 validation.");
  }
  static constexpr std::string_view kHexDigits = "0123456789abcdef";
  static constexpr auto kLowNibbleMask = 0x0FU;
  const auto length = static_cast<std::size_t>(digest_length);
  std::string output(length * 2U, '0');
  for (std::size_t index = 0; index < length; ++index) {
    output[index * 2U] = kHexDigits[digest[index] >> 4U];
    output[index * 2U + 1U] = kHexDigits[digest[index] & kLowNibbleMask];
  }
  return output;
}

auto readFile(const std::filesystem::path& path) -> std::string {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw TreeValidationError("supervisor.tree.unavailable", "Tree file is unavailable.");
  }
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

auto jsonEscape(const std::string& value) -> std::string {
  std::ostringstream output;
  for (const char character : value) {
    switch (character) {
      case '\\':
        output << "\\\\";
        break;
      case '"':
        output << "\\\"";
        break;
      case '\n':
        output << "\\n";
        break;
      case '\r':
        output << "\\r";
        break;
      case '\t':
        output << "\\t";
        break;
      default:
        output << character;
        break;
    }
  }
  return output.str();
}

auto nodeStatusName(BT::NodeStatus status) -> std::string {
  switch (status) {
    case BT::NodeStatus::IDLE:
      return "IDLE";
    case BT::NodeStatus::RUNNING:
      return "RUNNING";
    case BT::NodeStatus::SUCCESS:
      return "SUCCESS";
    case BT::NodeStatus::FAILURE:
      return "FAILURE";
    case BT::NodeStatus::SKIPPED:
      return "SKIPPED";
  }
  return "UNKNOWN";
}

auto durationToMilliseconds(const builtin_interfaces::msg::Duration& duration)
    -> std::chrono::milliseconds {
  const auto seconds = std::chrono::seconds(duration.sec);
  const auto nanoseconds = std::chrono::nanoseconds(duration.nanosec);
  return std::chrono::duration_cast<std::chrono::milliseconds>(seconds + nanoseconds);
}

}  // namespace

// ROS logging macros expand to nested control flow even though this constructor is linear.
// NOLINTNEXTLINE(readability-function-cognitive-complexity)
SupervisorNode::SupervisorNode(const rclcpp::NodeOptions& options)
    : rclcpp::Node("cell_supervisor", options) {
  tree_root_ = declare_parameter<std::string>("tree_root", "");
  cell_id_ = declare_parameter<std::string>("cell_id", "");
  const auto* active_bundle = std::getenv("CELLFORGE_BUNDLE_ID");
  bundle_id_ =
      declare_parameter<std::string>("bundle_id", active_bundle == nullptr ? "" : active_bundle);
  const auto action_name =
      declare_parameter<std::string>("action_name", "/cell/supervisor/run_job");
  default_job_timeout_ = std::chrono::milliseconds(
      declare_parameter<std::int64_t>("default_job_timeout_ms", kDefaultJobTimeout.count()));

  registerSupervisorNodes(factory_);

  state_publisher_ = create_publisher<cellforge_interfaces::msg::CellState>(
      "/cell/supervisor_state", rclcpp::QoS(kStateQueueDepth).reliable());
  event_publisher_ = create_publisher<cellforge_interfaces::msg::JobEvent>(
      "/events/job", rclcpp::QoS(kEventQueueDepth).reliable());
  cell_state_subscription_ = create_subscription<cellforge_interfaces::msg::CellState>(
      "/cell/state", rclcpp::QoS(kStateQueueDepth).reliable(),
      [this](const cellforge_interfaces::msg::CellState& message) { onCellState(message); });

  run_job_server_ = rclcpp_action::create_server<ExecuteFrozenJob>(
      this, action_name,
      [this](const rclcpp_action::GoalUUID& uuid,
             const std::shared_ptr<const ExecuteFrozenJob::Goal>& goal) {
        return handleGoal(uuid, goal);
      },
      [this](const std::shared_ptr<GoalHandleFrozenJob>& goal_handle) {
        return handleCancel(goal_handle);
      },
      [this](const std::shared_ptr<GoalHandleFrozenJob>& goal_handle) {
        handleAccepted(goal_handle);
      });

  worker_ = std::jthread([this](const std::stop_token& stop_token) { workerLoop(stop_token); });

  transitionState("IDLE");
  RCLCPP_INFO(get_logger(), "Supervisor ready; versioned tree root is '%s'.",
              tree_root_.string().c_str());
}

SupervisorNode::~SupervisorNode() {
  cancel_requested_.store(true);
  if (worker_.joinable()) {
    worker_.request_stop();
    worker_condition_.notify_all();
    worker_.join();
  }
}

// ROS warning macros dominate clang-tidy's expanded complexity; source-level validation is flat.
// NOLINTNEXTLINE(readability-function-cognitive-complexity)
auto SupervisorNode::handleGoal(const rclcpp_action::GoalUUID& /*unused*/,
                                const std::shared_ptr<const ExecuteFrozenJob::Goal>& goal)
    -> rclcpp_action::GoalResponse {
  if (!goal || !isUuid(goal->trace_id) || !isUuid(goal->job_id) || goal->cell_id.empty() ||
      goal->task_id.empty() || goal->recipe_id.empty() || !isSha256(goal->bundle_id) ||
      !isGitRevision(goal->source_revision) || !isSha256(goal->recipe_sha256) ||
      !isSha256(goal->task_sha256) ||
      goal->calibration_ids.size() != goal->calibration_sha256s.size() ||
      !std::all_of(goal->calibration_sha256s.begin(), goal->calibration_sha256s.end(), isSha256)) {
    RCLCPP_WARN(get_logger(), "Rejected frozen job with invalid immutable identity fields.");
    return rclcpp_action::GoalResponse::REJECT;
  }
  if (!cell_id_.empty() && goal->cell_id != cell_id_) {
    RCLCPP_WARN(get_logger(), "Rejected RunJob for a different cell ID.");
    return rclcpp_action::GoalResponse::REJECT;
  }
  if (!bundle_id_.empty() && goal->bundle_id != bundle_id_) {
    RCLCPP_WARN(get_logger(), "Rejected frozen job for a different active bundle.");
    return rclcpp_action::GoalResponse::REJECT;
  }

  bool expected = false;
  if (!job_active_.compare_exchange_strong(expected, true)) {
    RCLCPP_WARN(get_logger(), "Rejected RunJob because another job is active.");
    return rclcpp_action::GoalResponse::REJECT;
  }
  return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
}

auto SupervisorNode::handleCancel(const std::shared_ptr<GoalHandleFrozenJob>& /*unused*/)
    -> rclcpp_action::CancelResponse {
  if (!job_active_.load()) {
    return rclcpp_action::CancelResponse::REJECT;
  }
  cancel_requested_.store(true);
  return rclcpp_action::CancelResponse::ACCEPT;
}

void SupervisorNode::handleAccepted(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle) {
  cancel_requested_.store(false);
  {
    std::lock_guard lock(worker_mutex_);
    pending_goal_handle_ = goal_handle;
  }
  worker_condition_.notify_one();
}

void SupervisorNode::workerLoop(const std::stop_token& stop_token) {
  while (true) {
    std::shared_ptr<GoalHandleFrozenJob> goal_handle;
    {
      std::unique_lock lock(worker_mutex_);
      worker_condition_.wait(lock, stop_token,
                             [this]() { return pending_goal_handle_ != nullptr; });
      if (stop_token.stop_requested() && pending_goal_handle_ == nullptr) {
        return;
      }
      goal_handle = std::move(pending_goal_handle_);
    }
    executeGoal(goal_handle, stop_token);
  }
}

void SupervisorNode::executeGoal(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle,
                                 const std::stop_token& stop_token) {
  ScopeExit release_slot([this]() { finishGoalSlot(); });
  const auto release_goal_slot = [this, &release_slot]() {
    finishGoalSlot();
    release_slot.dismiss();
  };
  const auto goal = goal_handle->get_goal();
  const auto trace_id = goal->trace_id;
  current_identity_ = goal;
  auto result = std::make_shared<ExecuteFrozenJob::Result>();
  result->trace_id = trace_id;
  result->output_payload_json = "{}";

  publishEvent("job.accepted", goal->job_id, trace_id, "{}");
  if (!cell_ready_.load()) {
    result->success = false;
    result->result_code = "supervisor.job.cell_not_ready";
    result->result_message = "Aggregated cell and safety readiness is not healthy.";
    publishEvent("job.rejected", goal->job_id, trace_id,
                 R"({"code":"supervisor.job.cell_not_ready"})", {}, "WARN");
    release_goal_slot();
    goal_handle->abort(result);
    return;
  }

  auto blackboard = BT::Blackboard::create();
  blackboard->set("job_id", goal->job_id);
  blackboard->set("cell_id", goal->cell_id);
  blackboard->set("recipe_id", goal->recipe_id);
  blackboard->set("recipe_version", goal->recipe_version);
  blackboard->set("task_id", goal->task_id);
  blackboard->set("trace_id", goal->trace_id);
  blackboard->set("bundle_id", goal->bundle_id);
  blackboard->set("source_revision", goal->source_revision);
  blackboard->set("recipe_sha256", goal->recipe_sha256);
  blackboard->set("recipe_yaml", goal->recipe_yaml);
  blackboard->set("task_sha256", goal->task_sha256);
  blackboard->set("input_payload_json", goal->input_payload_json);
  blackboard->set("execution_mode", goal->execution_mode);
  blackboard->set("idempotency_key", goal->idempotency_key);
  blackboard->set("cell_ready", cell_ready_.load());
  blackboard->set<RosNodeWeakPtr>(kRosNodeBlackboardKey, RosNodeWeakPtr{shared_from_this()});

  std::optional<BT::Tree> tree;
  try {
    const auto tree_path = resolveTreePath(tree_root_, goal->task_id);
    if (sha256(goal->recipe_yaml) != goal->recipe_sha256) {
      throw TreeValidationError("supervisor.frozen.recipe_digest_mismatch",
                                "Frozen recipe content does not match its digest.");
    }
    if (sha256(readFile(tree_path)) != goal->task_sha256) {
      throw TreeValidationError("supervisor.frozen.task_digest_mismatch",
                                "Resolved task content does not match its digest.");
    }
    tree.emplace(createValidatedTreeFromFile(factory_, tree_path, blackboard));
  } catch (const TreeValidationError& error) {
    result->success = false;
    result->result_code = error.code();
    result->result_message = error.what();
    publishEvent("job.rejected", goal->job_id, trace_id,
                 R"({"code":")" + jsonEscape(error.code()) + R"(","message":")" +
                     jsonEscape(error.what()) + "\"}",
                 {}, "ERROR");
    release_goal_slot();
    goal_handle->abort(result);
    return;
  }

  auto transition_subscribers = attachTransitionEvents(*tree, goal->job_id, trace_id);
  (void)transition_subscribers;
  transitionState("RUNNING", goal->job_id, trace_id);
  publishEvent("job.started", goal->job_id, trace_id, "{}");

  auto job_timeout = durationToMilliseconds(goal->timeout);
  if (job_timeout <= 0ms) {
    job_timeout = default_job_timeout_;
  }
  const auto deadline = std::chrono::steady_clock::now() + job_timeout;

  BT::NodeStatus tree_status = BT::NodeStatus::IDLE;
  while (rclcpp::ok() && !stop_token.stop_requested()) {
    if (cancel_requested_.load()) {
      tree->haltTree();
      result->success = false;
      result->result_code = "supervisor.job.cancelled";
      result->result_message = "Job cancellation propagated to active behavior-tree actions.";
      publishEvent("job.cancelled", goal->job_id, trace_id, "{}", {}, "WARN");
      transitionState("IDLE", goal->job_id, trace_id);
      release_goal_slot();
      goal_handle->canceled(result);
      return;
    }
    if (std::chrono::steady_clock::now() >= deadline) {
      tree->haltTree();
      result->success = false;
      result->result_code = "supervisor.job.timeout";
      result->result_message = "Job deadline elapsed; active actions were cancelled.";
      publishEvent("job.failed", goal->job_id, trace_id, R"({"code":"supervisor.job.timeout"})", {},
                   "ERROR");
      transitionState("RECOVERABLE_FAULT", goal->job_id, trace_id);
      release_goal_slot();
      goal_handle->abort(result);
      return;
    }

    try {
      tree_status = tree->tickOnce();
    } catch (const std::exception& error) {
      tree->haltTree();
      result->success = false;
      result->result_code = "supervisor.tree.execution_error";
      result->result_message = error.what();
      publishEvent("job.failed", goal->job_id, trace_id,
                   R"({"code":"supervisor.tree.execution_error","message":")" +
                       jsonEscape(error.what()) + "\"}",
                   {}, "ERROR");
      transitionState("RECOVERABLE_FAULT", goal->job_id, trace_id);
      release_goal_slot();
      goal_handle->abort(result);
      return;
    }

    std::string active_node;
    tree->applyVisitor([&active_node](const BT::TreeNode* node) {
      if (active_node.empty() && node->status() == BT::NodeStatus::RUNNING) {
        active_node = node->fullPath();
      }
    });
    publishFeedback(goal_handle, "RUNNING", active_node, "Behavior tree is running.");

    if (tree_status == BT::NodeStatus::SUCCESS) {
      result->success = true;
      result->result_code = "supervisor.job.completed";
      result->result_message = "Behavior tree completed successfully.";
      publishEvent("job.completed", goal->job_id, trace_id, "{}");
      transitionState("IDLE", goal->job_id, trace_id);
      release_goal_slot();
      goal_handle->succeed(result);
      return;
    }
    if (tree_status == BT::NodeStatus::FAILURE) {
      result->success = false;
      result->result_code = "supervisor.job.tree_failed";
      result->result_message = "Behavior tree returned FAILURE.";
      publishEvent("job.failed", goal->job_id, trace_id, R"({"code":"supervisor.job.tree_failed"})",
                   {}, "ERROR");
      transitionState("RECOVERABLE_FAULT", goal->job_id, trace_id);
      release_goal_slot();
      goal_handle->abort(result);
      return;
    }
    std::this_thread::sleep_for(10ms);
  }

  if (tree) {
    tree->haltTree();
  }
  result->success = false;
  result->result_code = "supervisor.job.stopping";
  result->result_message = "Supervisor stopped while the job was active.";
  transitionState("STOPPING", goal->job_id, trace_id);
  release_goal_slot();
  goal_handle->abort(result);
}

void SupervisorNode::finishGoalSlot() {
  cancel_requested_.store(false);
  job_active_.store(false);
  current_identity_.reset();
}

void SupervisorNode::onCellState(const cellforge_interfaces::msg::CellState& message) {
  safety_healthy_.store(message.safety_healthy);
  required_devices_ready_.store(message.all_required_devices_ready);
  cell_ready_.store(message.state == "READY" && message.safety_healthy &&
                    message.all_required_devices_ready);
}

void SupervisorNode::transitionState(const std::string& state, const std::string& job_id,
                                     const std::string& trace_id) {
  {
    std::lock_guard lock(state_mutex_);
    state_ = state;
  }

  cellforge_interfaces::msg::CellState message;
  message.header.stamp = now();
  message.cell_id = cell_id_;
  message.state = state;
  message.safety_healthy = safety_healthy_.load();
  message.all_required_devices_ready = required_devices_ready_.load();
  message.active_job_id = state == "RUNNING" ? job_id : "";
  message.active_trace_id = state == "RUNNING" ? trace_id : "";
  message.bundle_id = current_identity_ ? current_identity_->bundle_id : bundle_id_;
  state_publisher_->publish(message);

  if (!job_id.empty() && !trace_id.empty()) {
    publishEvent("cell.state.changed", job_id, trace_id,
                 R"({"state":")" + jsonEscape(state) + "\"}");
  }
}

void SupervisorNode::publishEvent(const std::string& event_type, const std::string& job_id,
                                  const std::string& trace_id, const std::string& payload_json,
                                  const std::string& command_id, const std::string& severity) {
  cellforge_interfaces::msg::JobEvent event;
  event.header.stamp = now();
  event.trace_id = trace_id;
  event.job_id = job_id;
  event.cell_id = cell_id_;
  event.bundle_id = bundle_id_;
  if (current_identity_) {
    event.bundle_id = current_identity_->bundle_id;
    event.source_revision = current_identity_->source_revision;
    event.recipe_id = current_identity_->recipe_id;
    event.recipe_version = current_identity_->recipe_version;
    event.recipe_sha256 = current_identity_->recipe_sha256;
    event.task_id = current_identity_->task_id;
    event.task_sha256 = current_identity_->task_sha256;
    event.execution_mode = current_identity_->execution_mode;
    event.calibration_ids = current_identity_->calibration_ids;
    event.calibration_sha256s = current_identity_->calibration_sha256s;
  }
  event.command_id = command_id;
  event.sequence = 0;
  event.event_type = event_type;
  event.severity = severity;
  event.payload_json = payload_json;
  event_publisher_->publish(event);
}

auto SupervisorNode::attachTransitionEvents(BT::Tree& tree, const std::string& job_id,
                                            const std::string& trace_id)
    -> std::vector<BT::TreeNode::StatusChangeSubscriber> {
  std::vector<BT::TreeNode::StatusChangeSubscriber> subscribers;
  tree.applyVisitor([this, &subscribers, job_id, trace_id](BT::TreeNode* node) {
    subscribers.push_back(node->subscribeToStatusChange(
        [this, job_id, trace_id](BT::TimePoint, const BT::TreeNode& changed_node,
                                 BT::NodeStatus previous, BT::NodeStatus current) {
          const auto payload = R"({"node":")" + jsonEscape(changed_node.fullPath()) +
                               R"(","type":")" + jsonEscape(changed_node.registrationName()) +
                               R"(","previous":")" + nodeStatusName(previous) + R"(","current":")" +
                               nodeStatusName(current) + "\"}";
          if (previous == BT::NodeStatus::IDLE && current != BT::NodeStatus::IDLE) {
            publishEvent("behavior_tree.node.entered", job_id, trace_id, payload);
          }
          if (current == BT::NodeStatus::SUCCESS || current == BT::NodeStatus::FAILURE ||
              current == BT::NodeStatus::SKIPPED) {
            publishEvent("behavior_tree.node.completed", job_id, trace_id, payload);
          }
        }));
  });
  return subscribers;
}

void SupervisorNode::publishFeedback(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle,
                                     const std::string& state, const std::string& active_node,
                                     const std::string& message) {
  auto feedback = std::make_shared<ExecuteFrozenJob::Feedback>();
  feedback->cell_state = state;
  feedback->active_node = active_node;
  feedback->progress = 0.0F;
  feedback->message = message;
  goal_handle->publish_feedback(feedback);
}

}  // namespace cellforge_supervisor
