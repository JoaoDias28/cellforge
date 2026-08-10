#include "cellforge_motion/moveit_planner.hpp"

#include <moveit/task_constructor/task.h>

#include <chrono>
#include <exception>
#include <memory>
#include <moveit_msgs/msg/move_it_error_codes.hpp>
#include <stop_token>
#include <string>
#include <utility>
#include <vector>

namespace cellforge_motion {
namespace mtc = moveit::task_constructor;
namespace {
std::string moveItMessage(const moveit::core::MoveItErrorCode& code) {
  return "MoveIt error code " + std::to_string(code.val) + ".";
}
}  // namespace

MoveItPlanner::MoveItPlanner(rclcpp::Node::SharedPtr node, std::string planning_group)
    : node_(std::move(node)),
      planning_group_(std::move(planning_group)),
      move_group_(node_, planning_group_),
      task_builder_(node_, planning_group_) {}

PlannerResult MoveItPlanner::moveToPose(const MotionRequest& request, std::stop_token stop_token) {
  std::scoped_lock lock(mutex_);
  if (stop_token.stop_requested()) {
    return {PlannerOutcome::EXECUTION_FAILED, "Request cancelled before planning."};
  }
  move_group_.setMaxVelocityScalingFactor(request.max_velocity_scaling);
  move_group_.setMaxAccelerationScalingFactor(request.max_acceleration_scaling);
  move_group_.setPlanningTime(std::chrono::duration<double>(request.timeout).count());
  if (!request.named_pose.empty()) {
    move_group_.setNamedTarget(request.named_pose);
  } else {
    move_group_.setPoseTarget(request.target_pose);
  }

  moveit::planning_interface::MoveGroupInterface::Plan plan;
  const auto plan_code = move_group_.plan(plan);
  move_group_.clearPoseTargets();
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
  const auto execution_code = move_group_.execute(plan);
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
  result.completed_stages.push_back("execute");
  return result;
}

PlannerResult MoveItPlanner::executeManipulation(const ManipulationRequest& request,
                                                 std::stop_token stop_token) {
  std::scoped_lock lock(mutex_);
  const auto started = std::chrono::steady_clock::now();
  if (stop_token.stop_requested()) {
    return {PlannerOutcome::EXECUTION_FAILED, "Request cancelled before MTC planning."};
  }
  try {
    auto task = task_builder_.build(request);
    task->init();
    if (!task->plan(1) || task->solutions().empty()) {
      return {PlannerOutcome::PLANNING_FAILED,
              "MTC found no staged manipulation solution.",
              {},
              std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count(),
              {"current_state"},
              "staged_plan"};
    }
    PlannerResult result{PlannerOutcome::SUCCESS, "MTC staged manipulation plan completed."};
    result.planning_time_seconds =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    result.completed_stages = {"current_state", "approach_safe_pose", "move_to_object_pose",
                               "update_object_attachment", "retreat_to_safe_pose"};
    if (request.plan_only) {
      return result;
    }
    if (stop_token.stop_requested()) {
      return {PlannerOutcome::EXECUTION_FAILED,
              "Request cancelled before MTC execution.",
              {},
              result.planning_time_seconds,
              result.completed_stages,
              "execute"};
    }
    const auto execution_code = task->execute(*task->solutions().front());
    if (!execution_code) {
      result.outcome = mapMoveItCode(execution_code, true);
      result.message = moveItMessage(execution_code);
      result.failed_stage = "execute";
      result.outcome_certain = false;
      return result;
    }
    result.message = "MTC staged manipulation executed by the selected controller.";
    result.completed_stages.push_back("execute");
    return result;
  } catch (const mtc::InitStageException& error) {
    return {PlannerOutcome::INVALID_INPUT, error.what(), {}, 0.0, {}, "initialize"};
  } catch (const std::exception& error) {
    return {PlannerOutcome::PLANNING_FAILED, error.what(), {}, 0.0, {}, "staged_plan"};
  }
}

SceneSyncResult MoveItPlanner::syncPlanningScene(const SceneSyncRequest& request) {
  std::scoped_lock lock(mutex_);
  if (!planning_scene_.applyPlanningScene(request.planning_scene)) {
    return {false, "motion.scene.apply_failed", "MoveIt rejected the planning scene update."};
  }
  return {true, "motion.scene.synchronized", "Planning scene synchronized.",
          request.scene_revision};
}

void MoveItPlanner::cancelActiveRequest() { move_group_.stop(); }

PlannerOutcome MoveItPlanner::mapMoveItCode(const moveit::core::MoveItErrorCode& code,
                                            bool execution_phase) {
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
