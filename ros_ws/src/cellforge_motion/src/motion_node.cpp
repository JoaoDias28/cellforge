#include "cellforge_motion/motion_node.hpp"

#include <chrono>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

namespace cellforge_motion {
namespace {

constexpr std::size_t kEventQueueDepth = 100;

auto duration(const builtin_interfaces::msg::Duration& value) -> std::chrono::milliseconds {
  return std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::seconds(value.sec) + std::chrono::nanoseconds(value.nanosec));
}

auto operation(const std::string& value) -> ManipulationOperation {
  if (value == "pick") {
    return ManipulationOperation::PICK;
  }
  if (value == "load") {
    return ManipulationOperation::LOAD;
  }
  if (value == "unload") {
    return ManipulationOperation::UNLOAD;
  }
  return ManipulationOperation::PICK;
}

}  // namespace

MotionNode::MotionNode(std::shared_ptr<MotionService> service, const rclcpp::NodeOptions& options)
    : Node("motion_service", options), service_(std::move(service)) {
  if (!service_) {
    throw std::invalid_argument("motion service must not be null");
  }
  event_publisher_ = create_publisher<cellforge_interfaces::msg::JobEvent>(
      "/events/job", rclcpp::QoS(kEventQueueDepth).reliable());
  move_server_ = rclcpp_action::create_server<MoveToPose>(
      this, "/skills/move_to_pose",
      [this](const rclcpp_action::GoalUUID& uuid,
             const std::shared_ptr<const MoveToPose::Goal>& goal) {
        return handleMoveGoal(uuid, goal);
      },
      [](const std::shared_ptr<MoveGoalHandle>& goal) { return handleMoveCancel(goal); },
      [this](const std::shared_ptr<MoveGoalHandle>& goal) { handleMoveAccepted(goal); });
  manipulation_server_ = rclcpp_action::create_server<ExecuteManipulation>(
      this, "/skills/execute_manipulation",
      [this](const rclcpp_action::GoalUUID& uuid,
             const std::shared_ptr<const ExecuteManipulation::Goal>& goal) {
        return handleManipulationGoal(uuid, goal);
      },
      [](const std::shared_ptr<ManipulationGoalHandle>& goal) {
        return handleManipulationCancel(goal);
      },
      [this](const std::shared_ptr<ManipulationGoalHandle>& goal) {
        handleManipulationAccepted(goal);
      });
  scene_service_ = create_service<SyncPlanningScene>(
      "/motion/sync_planning_scene",
      [this](const std::shared_ptr<SyncPlanningScene::Request>& request,
             const std::shared_ptr<SyncPlanningScene::Response>& response) {
        syncScene(request, response);
      });
}

auto MotionNode::handleMoveGoal(const rclcpp_action::GoalUUID& uuid,
                                const std::shared_ptr<const MoveToPose::Goal>& goal)
    -> rclcpp_action::GoalResponse {
  static_cast<void>(uuid);
  static_cast<void>(goal);
  bool expected = false;
  return active_goal_.compare_exchange_strong(expected, true)
             ? rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE
             : rclcpp_action::GoalResponse::REJECT;
}

auto MotionNode::handleMoveCancel(const std::shared_ptr<MoveGoalHandle>& goal)
    -> rclcpp_action::CancelResponse {
  static_cast<void>(goal);
  return rclcpp_action::CancelResponse::ACCEPT;
}

void MotionNode::handleMoveAccepted(const std::shared_ptr<MoveGoalHandle>& goal) {
  std::thread([this, goal] { executeMove(goal); }).detach();
}

void MotionNode::executeMove(const std::shared_ptr<MoveGoalHandle>& goal_handle) {
  const auto goal = goal_handle->get_goal();
  auto feedback = std::make_shared<MoveToPose::Feedback>();
  feedback->phase = "planning";
  feedback->message = goal->plan_only ? "Planning without controller execution."
                                      : "Planning before controller execution.";
  goal_handle->publish_feedback(feedback);
  publishEvent("device.command.requested", goal->component_instance_id, goal->command_id,
               goal->trace_id, "INFO", "{}");
  MotionRequest request{goal->component_instance_id,
                        goal->command_id,
                        goal->trace_id,
                        goal->target_pose,
                        goal->named_pose,
                        goal->plan_only,
                        goal->max_velocity_scaling,
                        goal->max_acceleration_scaling,
                        duration(goal->timeout)};
  const auto outcome = service_->moveToPose(
      request, [goal_handle] { return goal_handle->is_canceling() || !rclcpp::ok(); });
  auto result = std::make_shared<MoveToPose::Result>();
  result->success = outcome.success;
  result->result_code = outcome.result_code;
  result->result_message = outcome.result_message;
  result->command_id = outcome.command_id;
  result->trace_id = outcome.trace_id;
  result->scene_revision = outcome.scene_revision;
  result->planning_time_seconds = outcome.planning_time_seconds;
  result->planned_trajectory = outcome.trajectory.joint_trajectory;
  result->evidence_json = outcome.evidence_json;
  result->outcome_certain = outcome.outcome_certain;
  publishEvent(outcome.success ? "device.command.completed" : "fault.raised",
               goal->component_instance_id, goal->command_id, goal->trace_id,
               outcome.success ? "INFO" : "ERROR", outcome.evidence_json);
  if (goal_handle->is_canceling() || outcome.result_code == "motion.request.cancelled") {
    goal_handle->canceled(result);
  } else if (outcome.success) {
    goal_handle->succeed(result);
  } else {
    goal_handle->abort(result);
  }
  active_goal_.store(false);
}

auto MotionNode::handleManipulationGoal(
    const rclcpp_action::GoalUUID& uuid,
    const std::shared_ptr<const ExecuteManipulation::Goal>& goal) -> rclcpp_action::GoalResponse {
  static_cast<void>(uuid);
  if (goal->operation != "pick" && goal->operation != "load" && goal->operation != "unload") {
    return rclcpp_action::GoalResponse::REJECT;
  }
  bool expected = false;
  return active_goal_.compare_exchange_strong(expected, true)
             ? rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE
             : rclcpp_action::GoalResponse::REJECT;
}

auto MotionNode::handleManipulationCancel(const std::shared_ptr<ManipulationGoalHandle>& goal)
    -> rclcpp_action::CancelResponse {
  static_cast<void>(goal);
  return rclcpp_action::CancelResponse::ACCEPT;
}

void MotionNode::handleManipulationAccepted(const std::shared_ptr<ManipulationGoalHandle>& goal) {
  std::thread([this, goal] { executeManipulation(goal); }).detach();
}

void MotionNode::executeManipulation(const std::shared_ptr<ManipulationGoalHandle>& goal_handle) {
  const auto goal = goal_handle->get_goal();
  auto feedback = std::make_shared<ExecuteManipulation::Feedback>();
  feedback->phase = "planning";
  feedback->active_stage = "current_state";
  feedback->message = "Building staged MTC manipulation task.";
  goal_handle->publish_feedback(feedback);
  ManipulationRequest request{goal->component_instance_id,
                              goal->command_id,
                              goal->trace_id,
                              operation(goal->operation),
                              goal->object_id,
                              goal->object_pose,
                              goal->tool_frame,
                              goal->named_safe_pose,
                              goal->plan_only,
                              goal->max_velocity_scaling,
                              goal->max_acceleration_scaling,
                              duration(goal->timeout)};
  const auto outcome = service_->executeManipulation(
      request, [goal_handle] { return goal_handle->is_canceling() || !rclcpp::ok(); });
  auto result = std::make_shared<ExecuteManipulation::Result>();
  result->success = outcome.success;
  result->result_code = outcome.result_code;
  result->result_message = outcome.result_message;
  result->command_id = outcome.command_id;
  result->trace_id = outcome.trace_id;
  result->scene_revision = outcome.scene_revision;
  result->planning_time_seconds = outcome.planning_time_seconds;
  result->completed_stages = outcome.completed_stages;
  result->failed_stage = outcome.failed_stage;
  result->evidence_json = outcome.evidence_json;
  result->outcome_certain = outcome.outcome_certain;
  publishEvent(outcome.success ? "device.command.completed" : "fault.raised",
               goal->component_instance_id, goal->command_id, goal->trace_id,
               outcome.success ? "INFO" : "ERROR", outcome.evidence_json);
  if (goal_handle->is_canceling() || outcome.result_code == "motion.request.cancelled") {
    goal_handle->canceled(result);
  } else if (outcome.success) {
    goal_handle->succeed(result);
  } else {
    goal_handle->abort(result);
  }
  active_goal_.store(false);
}

void MotionNode::syncScene(const std::shared_ptr<SyncPlanningScene::Request>& request,
                           const std::shared_ptr<SyncPlanningScene::Response>& response) {
  SceneSyncRequest update{
      request->cell_id,    request->scene_revision,         request->cell_yaml_sha256,
      request->usd_sha256, request->component_instance_ids, request->planning_scene};
  const auto outcome = service_->syncPlanningScene(update);
  response->success = outcome.success;
  response->result_code = outcome.result_code;
  response->result_message = outcome.result_message;
  response->applied_scene_revision = outcome.applied_scene_revision;
  response->evidence_json = outcome.evidence_json;
  publishEvent(outcome.success ? "motion.scene.synchronized" : "fault.raised", {}, {}, {},
               outcome.success ? "INFO" : "ERROR", outcome.evidence_json);
}

void MotionNode::publishEvent(const std::string& event_type,
                              const std::string& component_instance_id,
                              const std::string& command_id, const std::string& trace_id,
                              const std::string& severity, const std::string& evidence_json) {
  cellforge_interfaces::msg::JobEvent event;
  event.header.stamp = now();
  event.trace_id = trace_id;
  event.component_instance_id = component_instance_id;
  event.command_id = command_id;
  event.sequence = event_sequence_.fetch_add(1) + 1;
  event.event_type = event_type;
  event.severity = severity;
  event.payload_json = evidence_json;
  event_publisher_->publish(event);
}

}  // namespace cellforge_motion
