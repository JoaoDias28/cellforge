#include "cellforge_motion/moveit_planner.hpp"

#include <moveit/task_constructor/task.h>

#include <algorithm>
#include <chrono>
#include <exception>
#include <future>
#include <memory>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <stop_token>
#include <string>
#include <utility>
#include <vector>

namespace cellforge_motion {
namespace mtc = moveit::task_constructor;
namespace {
using namespace std::chrono_literals;

auto moveItMessage(const moveit::core::MoveItErrorCode& code) -> std::string {
  return "MoveIt error code " + std::to_string(code.val) + ".";
}

auto escapeJson(const std::string& value) -> std::string {
  std::string result;
  result.reserve(value.size());
  for (const auto character : value) {
    if (character == '\\' || character == '"') {
      result.push_back('\\');
    }
    result.push_back(character);
  }
  return result;
}

auto adapterOutcome(const std::string& code) -> PlannerOutcome {
  if (code == "motion.plan.collision") {
    return PlannerOutcome::COLLISION;
  }
  if (code == "simulation.pen.dropped" || code == "fixture.sensor.seating_failed" ||
      code == "motion.execution.failed") {
    return PlannerOutcome::EXECUTION_FAILED;
  }
  return PlannerOutcome::OUTCOME_UNKNOWN;
}

auto operationName(ManipulationOperation operation) -> const char* {
  switch (operation) {
    case ManipulationOperation::PICK:
      return "pick";
    case ManipulationOperation::LOAD:
      return "load";
    case ManipulationOperation::UNLOAD:
      return "unload";
  }
  return "";
}
}  // namespace

MoveItPlanner::MoveItPlanner(rclcpp::Node::SharedPtr node, std::string planning_group,
                             bool isaac_l2_direct)
    : node_(std::move(node)),
      planning_group_(std::move(planning_group)),
      isaac_l2_direct_(isaac_l2_direct),
      move_group_(isaac_l2_direct_
                      ? nullptr
                      : std::make_unique<moveit::planning_interface::MoveGroupInterface>(
                            node_, planning_group_)),
      planning_scene_interface_(
          isaac_l2_direct_
              ? nullptr
              : std::make_unique<moveit::planning_interface::PlanningSceneInterface>()),
      task_builder_(node_, planning_group_),
      isaac_adapter_(rclcpp_action::create_client<ExecuteSkill>(
          node_, "/device/robot_001/execute_trajectory")) {}

auto MoveItPlanner::moveToPose(const MotionRequest& request, std::stop_token stop_token)
    -> PlannerResult {
  std::scoped_lock lock(mutex_);
  if (stop_token.stop_requested()) {
    return {PlannerOutcome::EXECUTION_FAILED, "Request cancelled before planning."};
  }
  if (isaac_l2_direct_) {
    const auto started = std::chrono::steady_clock::now();
    try {
      auto task = task_builder_.buildMove(request, planning_scene_, false);
      task->init();
      if (!task->plan(1) || task->solutions().empty()) {
        return {PlannerOutcome::PLANNING_FAILED, "MTC found no move-to-pose solution."};
      }
      PlannerResult result{PlannerOutcome::SUCCESS, "MTC move-to-pose plan completed."};
      result.planning_time_seconds =
          std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
      result.completed_stages = {"validate_synchronized_scene"};
      if (request.plan_only) {
        return result;
      }
      auto adapter_result = executeInIsaac(
          request.command_id,
          R"({"mode":"move_to_pose","named_pose":")" + escapeJson(request.named_pose) + R"("})",
          request.timeout, stop_token);
      adapter_result.planning_time_seconds = result.planning_time_seconds;
      adapter_result.completed_stages = result.completed_stages;
      if (adapter_result.outcome == PlannerOutcome::SUCCESS) {
        adapter_result.completed_stages.emplace_back("isaac_physx_observation");
        adapter_result.message = "MTC plan executed and observed by the Isaac L2 adapter.";
      } else {
        adapter_result.failed_stage = "isaac_adapter";
      }
      return adapter_result;
    } catch (const std::exception& error) {
      return {PlannerOutcome::PLANNING_FAILED,
              error.what(),
              moveit_msgs::msg::RobotTrajectory(),
              0.0,
              {},
              "staged_plan"};
    }
  }
  move_group_->setMaxVelocityScalingFactor(request.max_velocity_scaling);
  move_group_->setMaxAccelerationScalingFactor(request.max_acceleration_scaling);
  move_group_->setPlanningTime(std::chrono::duration<double>(request.timeout).count());
  if (!request.named_pose.empty()) {
    move_group_->setNamedTarget(request.named_pose);
  } else {
    move_group_->setPoseTarget(request.target_pose);
  }

  moveit::planning_interface::MoveGroupInterface::Plan plan;
  const auto plan_code = move_group_->plan(plan);
  move_group_->clearPoseTargets();
  if (!plan_code) {
    return {mapMoveItCode(plan_code, false), moveItMessage(plan_code)};
  }
  PlannerResult result{PlannerOutcome::SUCCESS, "Collision-aware motion plan completed."};
  result.trajectory = plan.trajectory;
  result.planning_time_seconds = plan.planning_time;
  result.completed_stages = {"plan"};
  if (request.plan_only) {
    return result;
  }
  if (stop_token.stop_requested()) {
    return {PlannerOutcome::EXECUTION_FAILED, "Request cancelled before execution."};
  }
  const auto execution_code = move_group_->execute(plan);
  if (!execution_code) {
    return {mapMoveItCode(execution_code, true),
            moveItMessage(execution_code),
            plan.trajectory,
            plan.planning_time,
            {"plan"},
            "execute",
            false};
  }
  result.message = "Collision-aware plan executed by the selected trajectory controller.";
  result.completed_stages.emplace_back("execute");
  auto adapter_result = executeInIsaac(
      request.command_id,
      R"({"mode":"move_to_pose","named_pose":")" + escapeJson(request.named_pose) + R"("})",
      request.timeout, stop_token);
  if (adapter_result.outcome != PlannerOutcome::SUCCESS) {
    adapter_result.trajectory = plan.trajectory;
    adapter_result.planning_time_seconds = plan.planning_time;
    adapter_result.completed_stages = result.completed_stages;
    adapter_result.failed_stage = "isaac_adapter";
    return adapter_result;
  }
  result.completed_stages.emplace_back("isaac_physx_observation");
  result.message = "MoveIt plan executed and observed by the Isaac L2 adapter.";
  return result;
}

auto MoveItPlanner::executeManipulation(const ManipulationRequest& request,
                                        std::stop_token stop_token) -> PlannerResult {
  std::scoped_lock lock(mutex_);
  const auto started = std::chrono::steady_clock::now();
  if (stop_token.stop_requested()) {
    return {PlannerOutcome::EXECUTION_FAILED, "Request cancelled before MTC planning."};
  }
  try {
    auto task = task_builder_.build(request, planning_scene_, !isaac_l2_direct_);
    task->init();
    if (!task->plan(1) || task->solutions().empty()) {
      return {PlannerOutcome::PLANNING_FAILED,
              "MTC found no staged manipulation solution.",
              moveit_msgs::msg::RobotTrajectory(),
              std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count(),
              {"current_state"},
              "staged_plan"};
    }
    PlannerResult result{PlannerOutcome::SUCCESS, "MTC staged manipulation plan completed."};
    result.planning_time_seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    result.completed_stages = {"validate_synchronized_scene"};
    if (request.plan_only) {
      return result;
    }
    if (stop_token.stop_requested()) {
      return {PlannerOutcome::EXECUTION_FAILED,
              "Request cancelled before MTC execution.",
              moveit_msgs::msg::RobotTrajectory(),
              result.planning_time_seconds,
              result.completed_stages,
              "execute"};
    }
    if (!isaac_l2_direct_) {
      const auto execution_code = task->execute(*task->solutions().front());
      if (!execution_code) {
        result.outcome = mapMoveItCode(execution_code, true);
        result.message = moveItMessage(execution_code);
        result.failed_stage = "execute";
        result.outcome_certain = false;
        return result;
      }
      result.message = "MTC staged manipulation executed by the selected controller.";
      result.completed_stages.emplace_back("execute");
    }
    auto adapter_result = executeInIsaac(
        request.command_id,
        R"({"mode":"manipulation","operation":")" + escapeJson(operationName(request.operation)) +
            R"(","object_id":")" + escapeJson(request.object_id) + R"(","tool_frame":")" +
            escapeJson(request.tool_frame) + R"("})",
        request.timeout, stop_token);
    if (adapter_result.outcome != PlannerOutcome::SUCCESS) {
      adapter_result.planning_time_seconds = result.planning_time_seconds;
      adapter_result.completed_stages = result.completed_stages;
      adapter_result.failed_stage = "isaac_adapter";
      return adapter_result;
    }
    result.completed_stages.emplace_back("isaac_physx_observation");
    result.message = "MTC manipulation executed and observed by the Isaac L2 adapter.";
    return result;
  } catch (const mtc::InitStageException& error) {
    return {PlannerOutcome::INVALID_INPUT,
            error.what(),
            moveit_msgs::msg::RobotTrajectory(),
            0.0,
            {},
            "initialize"};
  } catch (const std::exception& error) {
    return {PlannerOutcome::PLANNING_FAILED,
            error.what(),
            moveit_msgs::msg::RobotTrajectory(),
            0.0,
            {},
            "staged_plan"};
  }
}

auto MoveItPlanner::executeInIsaac(const std::string& command_id, const std::string& payload,
                                   std::chrono::milliseconds timeout,
                                   const std::stop_token& stop_token) -> PlannerResult {
  if (!isaac_adapter_->wait_for_action_server(
          std::min(timeout, std::chrono::duration_cast<std::chrono::milliseconds>(5s)))) {
    return {PlannerOutcome::EXECUTION_FAILED, "Isaac L2 robot adapter is not ready."};
  }
  ExecuteSkill::Goal goal;
  goal.command_id = command_id;
  goal.skill_id = "robot_motion.action.execute_trajectory";
  goal.input_payload_json = payload;
  goal.execution_mode = "simulation";
  const auto timeout_seconds = std::chrono::duration_cast<std::chrono::seconds>(timeout);
  goal.timeout.sec = static_cast<std::int32_t>(timeout_seconds.count());
  goal.timeout.nanosec = static_cast<std::uint32_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(timeout - timeout_seconds).count());
  auto handle_future = isaac_adapter_->async_send_goal(goal);
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (handle_future.wait_for(10ms) != std::future_status::ready) {
    if (stop_token.stop_requested() || std::chrono::steady_clock::now() >= deadline) {
      return {PlannerOutcome::EXECUTION_FAILED,
              "Isaac L2 adapter goal was cancelled before acceptance."};
    }
  }
  const auto& handle = handle_future.get();
  if (!handle) {
    return {PlannerOutcome::EXECUTION_FAILED, "Isaac L2 adapter rejected the trajectory."};
  }
  {
    std::scoped_lock lock(action_mutex_);
    active_adapter_goal_ = handle;
  }
  auto result_future = isaac_adapter_->async_get_result(handle);
  while (result_future.wait_for(10ms) != std::future_status::ready) {
    if (stop_token.stop_requested() || std::chrono::steady_clock::now() >= deadline) {
      (void)isaac_adapter_->async_cancel_goal(handle);
      std::scoped_lock lock(action_mutex_);
      active_adapter_goal_.reset();
      return {PlannerOutcome::EXECUTION_FAILED, "Isaac L2 adapter execution timed out."};
    }
  }
  const auto& wrapped = result_future.get();
  {
    std::scoped_lock lock(action_mutex_);
    active_adapter_goal_.reset();
  }
  if (wrapped.code == rclcpp_action::ResultCode::SUCCEEDED && wrapped.result->success) {
    return {PlannerOutcome::SUCCESS, wrapped.result->result_message};
  }
  return {adapterOutcome(wrapped.result->result_code), wrapped.result->result_message};
}

auto MoveItPlanner::syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult {
  std::scoped_lock lock(mutex_);
  if (!isaac_l2_direct_ && !planning_scene_interface_->applyPlanningScene(request.planning_scene)) {
    return {false, "motion.scene.apply_failed", "MoveIt rejected the planning scene update."};
  }
  planning_scene_ = request.planning_scene;
  return {true, "motion.scene.synchronized", "Planning scene synchronized.",
          request.scene_revision};
}

void MoveItPlanner::cancelActiveRequest() {
  if (move_group_) {
    move_group_->stop();
  }
  std::scoped_lock lock(action_mutex_);
  if (active_adapter_goal_) {
    (void)isaac_adapter_->async_cancel_goal(active_adapter_goal_);
  }
}

auto MoveItPlanner::mapMoveItCode(const moveit::core::MoveItErrorCode& code, bool execution_phase)
    -> PlannerOutcome {
  using Codes = moveit_msgs::msg::MoveItErrorCodes;
  switch (code.val) {
    case Codes::SUCCESS:
      return PlannerOutcome::SUCCESS;
    case Codes::START_STATE_IN_COLLISION:
    case Codes::GOAL_IN_COLLISION:
    case Codes::GOAL_VIOLATES_PATH_CONSTRAINTS:
      return PlannerOutcome::COLLISION;
    case Codes::NO_IK_SOLUTION:
      return PlannerOutcome::UNREACHABLE;
    case Codes::INVALID_MOTION_PLAN:
    case Codes::INVALID_GOAL_CONSTRAINTS:
    case Codes::INVALID_GROUP_NAME:
    case Codes::INVALID_LINK_NAME:
      return PlannerOutcome::INVALID_INPUT;
    case Codes::CONTROL_FAILED:
      return PlannerOutcome::EXECUTION_FAILED;
    default:
      return execution_phase ? PlannerOutcome::OUTCOME_UNKNOWN : PlannerOutcome::PLANNING_FAILED;
  }
}

}  // namespace cellforge_motion
