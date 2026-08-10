#pragma once

#include <memory>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <mutex>
#include <rclcpp/rclcpp.hpp>
#include <string>

#include "cellforge_motion/motion_planner.hpp"
#include "cellforge_motion/mtc_task_builder.hpp"

namespace cellforge_motion {

class MoveItPlanner final : public MotionPlanner {
 public:
  MoveItPlanner(rclcpp::Node::SharedPtr node, std::string planning_group = "manipulator");
  auto moveToPose(const MotionRequest& request,
                  std::stop_token stop_token) -> PlannerResult override;
  auto executeManipulation(const ManipulationRequest& request,
                           std::stop_token stop_token) -> PlannerResult override;
  auto syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult override;
  void cancelActiveRequest() override;

 private:
  static auto mapMoveItCode(const moveit::core::MoveItErrorCode& code,
                            bool execution_phase) -> PlannerOutcome;

  rclcpp::Node::SharedPtr node_;
  std::string planning_group_;
  moveit::planning_interface::MoveGroupInterface move_group_;
  moveit::planning_interface::PlanningSceneInterface planning_scene_;
  MtcTaskBuilder task_builder_;
  std::mutex mutex_;
};

}  // namespace cellforge_motion
