#include "cellforge_pen_bt_nodes/pen_nodes.hpp"

#include <algorithm>
#include <array>
#include <builtin_interfaces/msg/duration.hpp>
#include <cstdint>
#include <iomanip>
#include <nlohmann/json.hpp>
#include <random>
#include <sstream>
#include <utility>

namespace cellforge_pen_bt_nodes {
namespace {

using Json = nlohmann::json;
constexpr std::int64_t kMillisecondsPerSecond = 1000;
constexpr std::int64_t kNanosecondsPerMillisecond = 1000000;
constexpr std::int64_t kLocateTimeoutMilliseconds = 3000;
constexpr std::int64_t kSkillTimeoutMilliseconds = 4000;
constexpr std::int64_t kInspectionTimeoutMilliseconds = 5000;
constexpr std::int64_t kProcessTimeoutMilliseconds = 15000;
constexpr std::int64_t kMotionTimeoutMilliseconds = 20000;
constexpr double kMotionScaling = 0.25;
constexpr std::size_t kUuidVersionIndex = 6;
constexpr std::size_t kUuidVariantIndex = 8;
constexpr std::uint8_t kUuidVersionMask = 0x0FU;
constexpr std::uint8_t kUuidVersionFour = 0x40U;
constexpr std::uint8_t kUuidVariantMask = 0x3FU;
constexpr std::uint8_t kUuidVariantRfc4122 = 0x80U;

auto duration(std::chrono::milliseconds timeout) -> builtin_interfaces::msg::Duration {
  builtin_interfaces::msg::Duration value;
  value.sec = static_cast<std::int32_t>(timeout.count() / kMillisecondsPerSecond);
  value.nanosec = static_cast<std::uint32_t>((timeout.count() % kMillisecondsPerSecond) *
                                             kNanosecondsPerMillisecond);
  return value;
}

auto actionSucceeded(bool success, rclcpp_action::ResultCode code) -> bool {
  return success && code == rclcpp_action::ResultCode::SUCCEEDED;
}

auto parseObject(const std::string& value) -> Json {
  const auto parsed = Json::parse(value);
  if (!parsed.is_object()) {
    throw BT::RuntimeError("Expected a JSON object.");
  }
  return parsed;
}

auto commonActionPorts(const std::string& action_name, std::int64_t timeout_ms) -> BT::PortsList {
  return {
      BT::InputPort<std::string>("action_name", action_name, "Typed ROS action endpoint."),
      BT::InputPort<std::int64_t>("timeout_ms", timeout_ms, "Positive steady deadline."),
  };
}

auto traceId(const BT::TreeNode& node) -> std::string {
  try {
    return node.config().blackboard->get<std::string>("trace_id");
  } catch (const std::exception&) {
    return {};
  }
}

}  // namespace

void recordOutcome(const BT::Blackboard::Ptr& blackboard, const std::string& code,
                   const std::string& message, bool outcome_certain) {
  blackboard->set("last_result_code", code);
  blackboard->set("last_result_message", message);
  blackboard->set("last_outcome_certain", outcome_certain);
}

ValidateFrozenJob::ValidateFrozenJob(const std::string& name, const BT::NodeConfig& config)
    : BT::ConditionNode(name, config) {}

auto ValidateFrozenJob::providedPorts() -> BT::PortsList {
  return {
      BT::InputPort<std::string>("job_id"),
      BT::InputPort<std::string>("cell_id"),
      BT::InputPort<std::string>("recipe_id"),
      BT::InputPort<std::uint32_t>("recipe_version"),
      BT::InputPort<std::string>("input_payload_json"),
      BT::InputPort<std::string>("execution_mode"),
  };
}

auto ValidateFrozenJob::tick() -> BT::NodeStatus {
  std::string job_id;
  std::string cell_id;
  std::string recipe_id;
  std::uint32_t recipe_version = 0;
  std::string payload;
  std::string execution_mode;
  const auto valid =
      getInput("job_id", job_id) && getInput("cell_id", cell_id) &&
      getInput("recipe_id", recipe_id) && getInput("recipe_version", recipe_version) &&
      getInput("input_payload_json", payload) && getInput("execution_mode", execution_mode);
  try {
    const auto input = parseObject(payload);
    if (!valid || job_id.empty() || cell_id.empty() || recipe_id.empty() || recipe_version == 0 ||
        execution_mode.empty() || !input.contains("engraving_text") ||
        !input.at("engraving_text").is_string() ||
        input.at("engraving_text").get_ref<const std::string&>().empty()) {
      throw BT::RuntimeError("Frozen pen job fields are incomplete.");
    }
  } catch (const std::exception& error) {
    recordOutcome(config().blackboard, "pen.job.invalid_frozen_input", error.what());
    return BT::NodeStatus::FAILURE;
  }
  recordOutcome(config().blackboard, "pen.job.validated", "Frozen pen job inputs are valid.");
  return BT::NodeStatus::SUCCESS;
}

CheckSafetyHealthy::CheckSafetyHealthy(const std::string& name, const BT::NodeConfig& config)
    : BT::ConditionNode(name, config) {}

auto CheckSafetyHealthy::providedPorts() -> BT::PortsList {
  return {BT::InputPort<bool>("healthy")};
}

auto CheckSafetyHealthy::tick() -> BT::NodeStatus {
  const auto healthy = getInput<bool>("healthy");
  if (!healthy || !healthy.value()) {
    recordOutcome(config().blackboard, "safety.unhealthy",
                  "Read-only safety status is unhealthy; normal execution is refused.");
    return BT::NodeStatus::FAILURE;
  }
  return BT::NodeStatus::SUCCESS;
}

CheckRequiredDevicesReady::CheckRequiredDevicesReady(const std::string& name,
                                                     const BT::NodeConfig& config)
    : BT::ConditionNode(name, config) {}

auto CheckRequiredDevicesReady::providedPorts() -> BT::PortsList {
  return {BT::InputPort<bool>("ready")};
}

auto CheckRequiredDevicesReady::tick() -> BT::NodeStatus {
  const auto ready = getInput<bool>("ready");
  if (!ready || !ready.value()) {
    recordOutcome(config().blackboard, "devices.not_ready", "Required devices are not ready.");
    return BT::NodeStatus::FAILURE;
  }
  return BT::NodeStatus::SUCCESS;
}

auto LocateProduct::providedPorts() -> BT::PortsList {
  auto ports = commonActionPorts("/device/camera-001/locate_object", kLocateTimeoutMilliseconds);
  ports.insert(BT::InputPort<std::string>("object_type"));
  ports.insert(BT::InputPort<std::string>("profile"));
  ports.insert(BT::OutputPort<geometry_msgs::msg::PoseStamped>("output_pose"));
  return ports;
}

auto LocateProduct::buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
    -> cellforge_interfaces::action::LocateObject::Goal {
  cellforge_interfaces::action::LocateObject::Goal goal;
  goal.command_id = command_id;
  if (!getInput("object_type", goal.object_type) || !getInput("profile", goal.profile_id)) {
    throw BT::RuntimeError("LocateProduct inputs could not be resolved.");
  }
  goal.region_of_interest_json = "{}";
  goal.timeout = duration(timeout);
  return goal;
}

auto LocateProduct::handleResult(const cellforge_interfaces::action::LocateObject::Result& result,
                                 rclcpp_action::ResultCode result_code) -> BT::NodeStatus {
  recordOutcome(config().blackboard, result.result_code, result.result_message);
  if (!actionSucceeded(result.success, result_code) || result.estimates.empty()) {
    return BT::NodeStatus::FAILURE;
  }
  (void)setOutput("output_pose", result.estimates.front().pose);
  return BT::NodeStatus::SUCCESS;
}

ManipulateProduct::ManipulateProduct(const std::string& name, const BT::NodeConfig& config,
                                     std::string operation)
    : TypedActionNode(name, config), operation_(std::move(operation)) {}

auto ManipulateProduct::commonPorts() -> BT::PortsList {
  return commonActionPorts("/skills/execute_manipulation", kMotionTimeoutMilliseconds);
}

auto ManipulateProduct::buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
    -> cellforge_interfaces::action::ExecuteManipulation::Goal {
  cellforge_interfaces::action::ExecuteManipulation::Goal goal;
  goal.component_instance_id = "robot-001";
  goal.command_id = command_id;
  goal.trace_id = traceId(*this);
  goal.operation = operation_;
  goal.object_id = "pen";
  goal.tool_frame = "tool0";
  goal.named_safe_pose = operation_ == "unload" ? "unload_safe" : "load_safe";
  goal.plan_only = false;
  goal.max_velocity_scaling = kMotionScaling;
  goal.max_acceleration_scaling = kMotionScaling;
  goal.timeout = duration(timeout);
  if (operation_ == "pick" && !getInput("pose", goal.object_pose)) {
    throw BT::RuntimeError("PickProduct pose could not be resolved.");
  }
  if (operation_ == "load") {
    std::string fixture;
    if (!getInput("fixture", fixture) || fixture.empty()) {
      throw BT::RuntimeError("LoadFixture fixture could not be resolved.");
    }
    goal.object_id = fixture;
  }
  return goal;
}

auto ManipulateProduct::handleResult(
    const cellforge_interfaces::action::ExecuteManipulation::Result& result,
    rclcpp_action::ResultCode result_code) -> BT::NodeStatus {
  recordOutcome(config().blackboard, result.result_code, result.result_message,
                result.outcome_certain);
  return actionSucceeded(result.success, result_code) ? BT::NodeStatus::SUCCESS
                                                      : BT::NodeStatus::FAILURE;
}

PickProduct::PickProduct(const std::string& name, const BT::NodeConfig& config)
    : ManipulateProduct(name, config, "pick") {}

auto PickProduct::providedPorts() -> BT::PortsList {
  auto ports = commonPorts();
  ports.insert(BT::InputPort<geometry_msgs::msg::PoseStamped>("pose"));
  return ports;
}

LoadFixture::LoadFixture(const std::string& name, const BT::NodeConfig& config)
    : ManipulateProduct(name, config, "load") {}

auto LoadFixture::providedPorts() -> BT::PortsList {
  auto ports = commonPorts();
  ports.insert(BT::InputPort<std::string>("fixture"));
  return ports;
}

UnloadProduct::UnloadProduct(const std::string& name, const BT::NodeConfig& config)
    : ManipulateProduct(name, config, "unload") {}

auto UnloadProduct::providedPorts() -> BT::PortsList { return commonPorts(); }

auto MoveRobotToProcessSafePose::providedPorts() -> BT::PortsList {
  auto ports = commonActionPorts("/skills/move_to_pose", kMotionTimeoutMilliseconds);
  ports.insert(BT::InputPort<std::string>("pose"));
  return ports;
}

auto MoveRobotToProcessSafePose::buildGoal(const std::string& command_id,
                                           std::chrono::milliseconds timeout)
    -> cellforge_interfaces::action::MoveToPose::Goal {
  cellforge_interfaces::action::MoveToPose::Goal goal;
  goal.component_instance_id = "robot-001";
  goal.command_id = command_id;
  goal.trace_id = traceId(*this);
  if (!getInput("pose", goal.named_pose)) {
    throw BT::RuntimeError("Process-safe pose could not be resolved.");
  }
  goal.plan_only = false;
  goal.max_velocity_scaling = kMotionScaling;
  goal.max_acceleration_scaling = kMotionScaling;
  goal.timeout = duration(timeout);
  return goal;
}

auto MoveRobotToProcessSafePose::handleResult(
    const cellforge_interfaces::action::MoveToPose::Result& result,
    rclcpp_action::ResultCode result_code) -> BT::NodeStatus {
  recordOutcome(config().blackboard, result.result_code, result.result_message,
                result.outcome_certain);
  return actionSucceeded(result.success, result_code) ? BT::NodeStatus::SUCCESS
                                                      : BT::NodeStatus::FAILURE;
}

ExecuteSkillLeaf::ExecuteSkillLeaf(const std::string& name, const BT::NodeConfig& config,
                                   std::string skill_id)
    : TypedActionNode(name, config), skill_id_(std::move(skill_id)) {}

auto ExecuteSkillLeaf::commonPorts() -> BT::PortsList {
  return commonActionPorts("/device/unknown/execute_skill", kSkillTimeoutMilliseconds);
}

auto ExecuteSkillLeaf::buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
    -> cellforge_interfaces::action::ExecuteSkill::Goal {
  cellforge_interfaces::action::ExecuteSkill::Goal goal;
  goal.command_id = command_id;
  goal.skill_id = skill_id_;
  goal.input_payload_json = inputPayload();
  goal.execution_mode = config().blackboard->get<std::string>("execution_mode");
  goal.timeout = duration(timeout);
  return goal;
}

auto ExecuteSkillLeaf::handleResult(
    const cellforge_interfaces::action::ExecuteSkill::Result& result,
    rclcpp_action::ResultCode result_code) -> BT::NodeStatus {
  recordOutcome(config().blackboard, result.result_code, result.result_message);
  return actionSucceeded(result.success, result_code) ? BT::NodeStatus::SUCCESS
                                                      : BT::NodeStatus::FAILURE;
}

VerifyFixture::VerifyFixture(const std::string& name, const BT::NodeConfig& config)
    : ExecuteSkillLeaf(name, config, "fixture.action.verify_seated") {}

auto VerifyFixture::providedPorts() -> BT::PortsList {
  auto ports = commonPorts();
  ports.erase("action_name");
  ports.insert(BT::InputPort<std::string>("action_name", "/device/fixture-001/verify_seated",
                                          "Typed ROS action endpoint."));
  ports.insert(BT::InputPort<std::string>("fixture"));
  return ports;
}

auto VerifyFixture::inputPayload() -> std::string {
  std::string fixture;
  if (!getInput("fixture", fixture)) {
    throw BT::RuntimeError("VerifyFixture fixture could not be resolved.");
  }
  return Json({{"fixture_id", fixture}}).dump();
}

SelectProcessProgram::SelectProcessProgram(const std::string& name, const BT::NodeConfig& config)
    : ExecuteSkillLeaf(name, config, "process.action.select_program") {}

auto SelectProcessProgram::providedPorts() -> BT::PortsList {
  auto ports = commonPorts();
  ports.erase("action_name");
  ports.insert(BT::InputPort<std::string>("action_name", "/device/laser-001/select_program",
                                          "Typed ROS action endpoint."));
  ports.insert(BT::InputPort<std::string>("program"));
  ports.insert(BT::InputPort<std::string>("variable_data"));
  return ports;
}

auto SelectProcessProgram::inputPayload() -> std::string {
  std::string program;
  std::string variable_data;
  if (!getInput("program", program) || !getInput("variable_data", variable_data)) {
    throw BT::RuntimeError("SelectProcessProgram inputs could not be resolved.");
  }
  return Json({{"program_id", program}, {"variable_data", parseObject(variable_data)}}).dump();
}

auto ExecuteProcess::providedPorts() -> BT::PortsList {
  auto ports = commonActionPorts("/device/laser-001/execute_cycle", kProcessTimeoutMilliseconds);
  ports.insert(BT::InputPort<std::string>("program"));
  ports.insert(BT::InputPort<std::string>("variable_data"));
  ports.insert(BT::InputPort<std::string>("recipe_id"));
  ports.insert(BT::InputPort<std::uint32_t>("recipe_version"));
  return ports;
}

auto ExecuteProcess::buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
    -> cellforge_interfaces::action::ExecuteProcess::Goal {
  cellforge_interfaces::action::ExecuteProcess::Goal goal;
  goal.command_id = command_id;
  if (!getInput("program", goal.program_id) ||
      !getInput("variable_data", goal.variable_data_json) ||
      !getInput("recipe_id", goal.recipe_id) || !getInput("recipe_version", goal.recipe_version)) {
    throw BT::RuntimeError("ExecuteProcess inputs could not be resolved.");
  }
  (void)parseObject(goal.variable_data_json);
  goal.timeout = duration(timeout);
  return goal;
}

auto ExecuteProcess::handleResult(
    const cellforge_interfaces::action::ExecuteProcess::Result& result,
    rclcpp_action::ResultCode result_code) -> BT::NodeStatus {
  recordOutcome(config().blackboard, result.result_code, result.result_message,
                result.outcome_certain);
  if (!result.outcome_certain) {
    config().blackboard->set("process_outcome_unknown", true);
    return BT::NodeStatus::FAILURE;
  }
  return actionSucceeded(result.success, result_code) ? BT::NodeStatus::SUCCESS
                                                      : BT::NodeStatus::FAILURE;
}

auto ExecuteProcess::handleDeadline() -> BT::NodeStatus {
  config().blackboard->set("process_outcome_unknown", true);
  recordOutcome(
      config().blackboard, "laser.process.outcome_unknown",
      "Process deadline elapsed after dispatch; physical outcome requires reconciliation.", false);
  return BT::NodeStatus::FAILURE;
}

auto InspectProduct::providedPorts() -> BT::PortsList {
  auto ports =
      commonActionPorts("/device/camera-001/inspect_object", kInspectionTimeoutMilliseconds);
  ports.insert(BT::InputPort<std::string>("profile"));
  ports.insert(BT::InputPort<std::string>("expected"));
  ports.insert(BT::OutputPort<std::string>("measurements"));
  return ports;
}

auto InspectProduct::buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
    -> cellforge_interfaces::action::InspectObject::Goal {
  cellforge_interfaces::action::InspectObject::Goal goal;
  goal.command_id = command_id;
  if (!getInput("profile", goal.inspection_profile) || !getInput("expected", goal.expected_json)) {
    throw BT::RuntimeError("InspectProduct inputs could not be resolved.");
  }
  (void)parseObject(goal.expected_json);
  goal.timeout = duration(timeout);
  return goal;
}

auto InspectProduct::handleResult(const cellforge_interfaces::action::InspectObject::Result& result,
                                  rclcpp_action::ResultCode result_code) -> BT::NodeStatus {
  recordOutcome(config().blackboard, result.result_code, result.result_message);
  const auto inspection = Json({{"accepted", result.accepted},
                                {"measurements", parseObject(result.measurements_json)},
                                {"evidence_uri", result.evidence_uri}})
                              .dump();
  (void)setOutput("measurements", inspection);
  return actionSucceeded(result.success, result_code) && result.accepted ? BT::NodeStatus::SUCCESS
                                                                         : BT::NodeStatus::FAILURE;
}

RouteByInspection::RouteByInspection(const std::string& name, const BT::NodeConfig& config)
    : BT::ConditionNode(name, config) {}

auto RouteByInspection::providedPorts() -> BT::PortsList {
  return {BT::InputPort<std::string>("inspection")};
}

auto RouteByInspection::tick() -> BT::NodeStatus {
  std::string inspection;
  try {
    if (!getInput("inspection", inspection) || !parseObject(inspection).value("accepted", false)) {
      recordOutcome(config().blackboard, "inspection.rejected",
                    "Inspection did not authorize pass routing.");
      return BT::NodeStatus::FAILURE;
    }
  } catch (const std::exception& error) {
    recordOutcome(config().blackboard, "inspection.invalid", error.what());
    return BT::NodeStatus::FAILURE;
  }
  return BT::NodeStatus::SUCCESS;
}

RecordProductionResult::RecordProductionResult(const std::string& name,
                                               const BT::NodeConfig& config)
    : BT::SyncActionNode(name, config) {}

auto RecordProductionResult::providedPorts() -> BT::PortsList { return {}; }

auto RecordProductionResult::tick() -> BT::NodeStatus {
  config().blackboard->set("production_result_recorded", true);
  recordOutcome(config().blackboard, "production.result.recorded",
                "Production result is ready for the recorder.");
  return BT::NodeStatus::SUCCESS;
}

void registerPenNodes(BT::BehaviorTreeFactory& factory) {
  factory.registerNodeType<ValidateFrozenJob>("ValidateFrozenJob");
  factory.registerNodeType<CheckSafetyHealthy>("CheckSafetyHealthy");
  factory.registerNodeType<CheckRequiredDevicesReady>("CheckRequiredDevicesReady");
  factory.registerNodeType<LocateProduct>("LocateProduct");
  factory.registerNodeType<PickProduct>("PickProduct");
  factory.registerNodeType<LoadFixture>("LoadFixture");
  factory.registerNodeType<VerifyFixture>("VerifyFixture");
  factory.registerNodeType<MoveRobotToProcessSafePose>("MoveRobotToProcessSafePose");
  factory.registerNodeType<SelectProcessProgram>("SelectProcessProgram");
  factory.registerNodeType<ExecuteProcess>("ExecuteProcess");
  factory.registerNodeType<InspectProduct>("InspectProduct");
  factory.registerNodeType<UnloadProduct>("UnloadProduct");
  factory.registerNodeType<RouteByInspection>("RouteByInspection");
  factory.registerNodeType<RecordProductionResult>("RecordProductionResult");
}

auto newCommandId() -> std::string {
  constexpr std::size_t kByteCount = 16;
  constexpr std::array<std::size_t, 4> kHyphens{3, 5, 7, 9};
  std::array<std::uint8_t, kByteCount> bytes{};
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
    if (std::find(kHyphens.begin(), kHyphens.end(), index) != kHyphens.end()) {
      output << '-';
    }
  }
  return output.str();
}

}  // namespace cellforge_pen_bt_nodes
