#pragma once

#include <atomic>
#include <cellforge_interfaces/action/execute_manipulation.hpp>
#include <cellforge_interfaces/action/move_to_pose.hpp>
#include <cellforge_interfaces/msg/job_event.hpp>
#include <cellforge_interfaces/srv/sync_planning_scene.hpp>
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>

#include "cellforge_motion/motion_service.hpp"

namespace cellforge_motion {

class MotionNode final : public rclcpp::Node {
 public:
  explicit MotionNode(std::shared_ptr<MotionService> service,
                      const rclcpp::NodeOptions& options = rclcpp::NodeOptions());

 private:
  using MoveToPose = cellforge_interfaces::action::MoveToPose;
  using MoveGoalHandle = rclcpp_action::ServerGoalHandle<MoveToPose>;
  using ExecuteManipulation = cellforge_interfaces::action::ExecuteManipulation;
  using ManipulationGoalHandle = rclcpp_action::ServerGoalHandle<ExecuteManipulation>;
  using SyncPlanningScene = cellforge_interfaces::srv::SyncPlanningScene;

  rclcpp_action::GoalResponse handleMoveGoal(const rclcpp_action::GoalUUID& uuid,
                                             std::shared_ptr<const MoveToPose::Goal> goal);
  rclcpp_action::CancelResponse handleMoveCancel(const std::shared_ptr<MoveGoalHandle> goal);
  void handleMoveAccepted(const std::shared_ptr<MoveGoalHandle> goal);
  void executeMove(const std::shared_ptr<MoveGoalHandle> goal_handle);

  rclcpp_action::GoalResponse handleManipulationGoal(
      const rclcpp_action::GoalUUID& uuid, std::shared_ptr<const ExecuteManipulation::Goal> goal);
  rclcpp_action::CancelResponse handleManipulationCancel(
      const std::shared_ptr<ManipulationGoalHandle> goal);
  void handleManipulationAccepted(const std::shared_ptr<ManipulationGoalHandle> goal);
  void executeManipulation(const std::shared_ptr<ManipulationGoalHandle> goal_handle);
  void syncScene(const std::shared_ptr<SyncPlanningScene::Request> request,
                 std::shared_ptr<SyncPlanningScene::Response> response);
  void publishEvent(const std::string& event_type, const std::string& component_instance_id,
                    const std::string& command_id, const std::string& trace_id,
                    const std::string& severity, const std::string& evidence_json);

  std::shared_ptr<MotionService> service_;
  std::atomic_bool active_goal_{false};
  std::atomic_uint64_t event_sequence_{0};
  rclcpp_action::Server<MoveToPose>::SharedPtr move_server_;
  rclcpp_action::Server<ExecuteManipulation>::SharedPtr manipulation_server_;
  rclcpp::Service<SyncPlanningScene>::SharedPtr scene_service_;
  rclcpp::Publisher<cellforge_interfaces::msg::JobEvent>::SharedPtr event_publisher_;
};

}  // namespace cellforge_motion
