#pragma once

#include <memory>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <mutex>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>

#include "cellforge_interfaces/action/execute_skill.hpp"
#include "cellforge_motion/motion_planner.hpp"
#include "cellforge_motion/mtc_task_builder.hpp"

namespace cellforge_motion {

class MoveItPlanner final : public MotionPlanner {
 public:
  MoveItPlanner(rclcpp::Node::SharedPtr node, std::string planning_group = "manipulator",
                bool isaac_l2_direct = false);
  auto moveToPose(const MotionRequest& request, std::stop_token stop_token)
      -> PlannerResult override;
  auto executeManipulation(const ManipulationRequest& request, std::stop_token stop_token)
      -> PlannerResult override;
  auto syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult override;
  void cancelActiveRequest() override;

 private:
  using ExecuteSkill = cellforge_interfaces::action::ExecuteSkill;
  using AdapterGoalHandle = rclcpp_action::ClientGoalHandle<ExecuteSkill>;

  auto executeInIsaac(const std::string& command_id, const std::string& payload,
                      std::chrono::milliseconds timeout, const std::stop_token& stop_token)
      -> PlannerResult;
  static auto mapMoveItCode(const moveit::core::MoveItErrorCode& code, bool execution_phase)
      -> PlannerOutcome;

  rclcpp::Node::SharedPtr node_;
  std::string planning_group_;
  bool isaac_l2_direct_;
  std::unique_ptr<moveit::planning_interface::MoveGroupInterface> move_group_;
  std::unique_ptr<moveit::planning_interface::PlanningSceneInterface> planning_scene_interface_;
  moveit_msgs::msg::PlanningScene planning_scene_;
  MtcTaskBuilder task_builder_;
  rclcpp_action::Client<ExecuteSkill>::SharedPtr isaac_adapter_;
  std::mutex action_mutex_;
  AdapterGoalHandle::SharedPtr active_adapter_goal_;
  std::mutex mutex_;
};

}  // namespace cellforge_motion
