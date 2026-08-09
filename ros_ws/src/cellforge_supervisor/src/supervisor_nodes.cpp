#include "cellforge_supervisor/supervisor_nodes.hpp"

#include <algorithm>
#include <array>
#include <builtin_interfaces/msg/duration.hpp>
#include <cstdint>
#include <iomanip>
#include <random>
#include <sstream>
#include <utility>

namespace cellforge_supervisor {
namespace {

constexpr std::int64_t kDefaultSkillTimeoutMilliseconds = 30000;
constexpr std::int64_t kMillisecondsPerSecond = 1000;
constexpr std::int64_t kNanosecondsPerMillisecond = 1000000;
constexpr std::size_t kUuidByteCount = 16;
constexpr std::size_t kUuidVersionIndex = 6;
constexpr std::size_t kUuidVariantIndex = 8;
constexpr std::uint8_t kUuidVersionMask = 0x0F;
constexpr std::uint8_t kUuidVersionFour = 0x40;
constexpr std::uint8_t kUuidVariantMask = 0x3F;
constexpr std::uint8_t kUuidVariantRfc4122 = 0x80;
constexpr std::array<std::size_t, 4> kUuidHyphenPositions{3, 5, 7, 9};

}  // namespace

CellReadyCondition::CellReadyCondition(const std::string& name, const BT::NodeConfig& config)
    : BT::ConditionNode(name, config) {}

auto CellReadyCondition::providedPorts() -> BT::PortsList {
  return {BT::InputPort<bool>("cell_ready")};
}

auto CellReadyCondition::tick() -> BT::NodeStatus {
  const auto ready = getInput<bool>("cell_ready");
  if (!ready) {
    throw BT::RuntimeError("CellReady missing required input [cell_ready]: ", ready.error());
  }
  return ready.value() ? BT::NodeStatus::SUCCESS : BT::NodeStatus::FAILURE;
}

ExecuteSkillAction::ExecuteSkillAction(const std::string& name, const BT::NodeConfig& config)
    : BT::StatefulActionNode(name, config) {}

auto ExecuteSkillAction::providedPorts() -> BT::PortsList {
  return {
      BT::InputPort<std::string>("action_name"),
      BT::InputPort<std::string>("skill_id"),
      BT::InputPort<std::string>("input_payload_json", std::string("{}"), ""),
      BT::InputPort<std::string>("execution_mode"),
      BT::InputPort<std::string>("command_id", std::string(""), ""),
      BT::InputPort<std::int64_t>("timeout_ms", kDefaultSkillTimeoutMilliseconds, ""),
      BT::OutputPort<std::string>("resolved_command_id"),
      BT::OutputPort<std::string>("result_code"),
      BT::OutputPort<std::string>("result_message"),
      BT::OutputPort<std::string>("output_payload_json"),
  };
}

auto ExecuteSkillAction::onStart() -> BT::NodeStatus {
  std::string action_name;
  std::string skill_id;
  std::string input_payload_json;
  std::string execution_mode;
  std::string command_id;
  std::int64_t timeout_ms = 0;

  const auto action_input = getInput("action_name", action_name);
  const auto skill_input = getInput("skill_id", skill_id);
  const auto payload_input = getInput("input_payload_json", input_payload_json);
  const auto mode_input = getInput("execution_mode", execution_mode);
  const auto command_input = getInput("command_id", command_id);
  const auto timeout_input = getInput("timeout_ms", timeout_ms);
  if (!action_input || !skill_input || !payload_input || !mode_input || !command_input ||
      !timeout_input) {
    return fail("supervisor.capability.invalid_ports", "ExecuteSkill input resolution failed.");
  }
  if (action_name.empty() || skill_id.empty() || execution_mode.empty() || timeout_ms <= 0) {
    return fail("supervisor.capability.invalid_input",
                "action_name, skill_id, execution_mode, and a positive timeout are required.");
  }
  if (command_id.empty()) {
    command_id = newUuid();
  }
  (void)setOutput("resolved_command_id", command_id);

  rclcpp::Node::SharedPtr node;
  try {
    node = config().blackboard->get<RosNodeWeakPtr>(kRosNodeBlackboardKey).lock();
  } catch (const std::exception& error) {
    return fail("supervisor.capability.no_ros_node", error.what());
  }
  if (!node) {
    return fail("supervisor.capability.no_ros_node", "ROS node blackboard entry is null.");
  }

  client_ = rclcpp_action::create_client<ExecuteSkill>(node, action_name);
  state_ = std::make_shared<AsyncState>();
  goal_sent_ = false;
  deadline_ = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);

  pending_goal_.command_id = command_id;
  pending_goal_.skill_id = skill_id;
  pending_goal_.input_payload_json = input_payload_json;
  pending_goal_.execution_mode = execution_mode;
  pending_goal_.timeout.sec = static_cast<std::int32_t>(timeout_ms / kMillisecondsPerSecond);
  pending_goal_.timeout.nanosec = static_cast<std::uint32_t>((timeout_ms % kMillisecondsPerSecond) *
                                                             kNanosecondsPerMillisecond);
  if (client_->action_server_is_ready()) {
    sendGoal();
  }
  return BT::NodeStatus::RUNNING;
}

void ExecuteSkillAction::sendGoal() {
  auto state = state_;
  auto client = client_;
  rclcpp_action::Client<ExecuteSkill>::SendGoalOptions options;
  options.goal_response_callback = [state, client](const GoalHandle::SharedPtr& goal_handle) {
    bool cancel_after_accept = false;
    {
      std::lock_guard lock(state->mutex);
      state->goal_handle = goal_handle;
      state->goal_rejected = !goal_handle;
      cancel_after_accept = goal_handle && state->cancel_requested && !state->cancel_sent;
      if (cancel_after_accept) {
        state->cancel_sent = true;
      }
    }
    if (cancel_after_accept) {
      (void)client->async_cancel_goal(goal_handle);
    }
  };
  options.result_callback = [state](const GoalHandle::WrappedResult& wrapped_result) {
    std::lock_guard lock(state->mutex);
    state->result_code = wrapped_result.code;
    state->result = wrapped_result.result;
  };
  goal_sent_ = true;
  (void)client_->async_send_goal(pending_goal_, options);
}

auto ExecuteSkillAction::onRunning() -> BT::NodeStatus {
  const auto state = state_;
  if (!state) {
    return fail("supervisor.capability.internal", "ExecuteSkill has no active state.");
  }

  if (std::chrono::steady_clock::now() >= deadline_) {
    requestCancellation(state);
    return fail(goal_sent_ ? "supervisor.capability.timeout" : "supervisor.capability.unavailable",
                goal_sent_
                    ? "ExecuteSkill exceeded its supervisor deadline; cancellation was requested."
                    : "ExecuteSkill action server was not ready before the deadline.");
  }
  if (!goal_sent_) {
    if (client_ && client_->action_server_is_ready()) {
      sendGoal();
    }
    return BT::NodeStatus::RUNNING;
  }

  std::shared_ptr<const ExecuteSkill::Result> result;
  rclcpp_action::ResultCode result_code = rclcpp_action::ResultCode::UNKNOWN;
  bool goal_rejected = false;
  {
    std::lock_guard lock(state->mutex);
    result = state->result;
    result_code = state->result_code;
    goal_rejected = state->goal_rejected;
  }

  if (goal_rejected) {
    return fail("supervisor.capability.rejected", "ExecuteSkill goal was rejected.");
  }
  if (!result) {
    return BT::NodeStatus::RUNNING;
  }

  (void)setOutput("result_code", result->result_code);
  (void)setOutput("result_message", result->result_message);
  (void)setOutput("output_payload_json", result->output_payload_json);
  if (result_code == rclcpp_action::ResultCode::SUCCEEDED && result->success) {
    return BT::NodeStatus::SUCCESS;
  }
  if (result_code == rclcpp_action::ResultCode::CANCELED) {
    return fail("supervisor.capability.cancelled", result->result_message);
  }
  return BT::NodeStatus::FAILURE;
}

void ExecuteSkillAction::onHalted() {
  if (state_) {
    requestCancellation(state_);
  }
}

void ExecuteSkillAction::requestCancellation(const std::shared_ptr<AsyncState>& state) {
  GoalHandle::SharedPtr goal_handle;
  {
    std::lock_guard lock(state->mutex);
    state->cancel_requested = true;
    if (state->goal_handle && !state->cancel_sent) {
      state->cancel_sent = true;
      goal_handle = state->goal_handle;
    }
  }
  if (goal_handle && client_) {
    (void)client_->async_cancel_goal(goal_handle);
  }
}

auto ExecuteSkillAction::fail(const std::string& code,
                              const std::string& message) -> BT::NodeStatus {
  (void)setOutput("result_code", code);
  (void)setOutput("result_message", message);
  (void)setOutput("output_payload_json", "{}");
  return BT::NodeStatus::FAILURE;
}

void registerSupervisorNodes(BT::BehaviorTreeFactory& factory) {
  factory.registerNodeType<CellReadyCondition>("CellReady");
  factory.registerNodeType<ExecuteSkillAction>("ExecuteSkill");
}

auto newUuid() -> std::string {
  std::array<std::uint8_t, kUuidByteCount> bytes{};
  std::random_device random;
  for (auto& value : bytes) {
    value = static_cast<std::uint8_t>(random());
  }
  bytes[kUuidVersionIndex] =
      static_cast<std::uint8_t>((bytes[kUuidVersionIndex] & kUuidVersionMask) | kUuidVersionFour);
  bytes[kUuidVariantIndex] = static_cast<std::uint8_t>(
      (bytes[kUuidVariantIndex] & kUuidVariantMask) | kUuidVariantRfc4122);

  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (std::size_t index = 0; index < bytes.size(); ++index) {
    output << std::setw(2) << static_cast<unsigned int>(bytes[index]);
    if (std::find(kUuidHyphenPositions.begin(), kUuidHyphenPositions.end(), index) !=
        kUuidHyphenPositions.end()) {
      output << '-';
    }
  }
  return output.str();
}

}  // namespace cellforge_supervisor
