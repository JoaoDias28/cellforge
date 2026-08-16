#pragma once

#include <memory>
#include <rclcpp/rclcpp.hpp>

#include "cellforge_motion/motion_types.hpp"

namespace moveit::task_constructor {
class Task;
}

namespace cellforge_motion {

class MtcTaskBuilder {
 public:
  MtcTaskBuilder(rclcpp::Node::SharedPtr node, std::string planning_group);
  [[nodiscard]] auto build(const ManipulationRequest& request,
                           const moveit_msgs::msg::PlanningScene& scene,
                           bool include_live_stages = true) const
      -> std::unique_ptr<moveit::task_constructor::Task>;
  [[nodiscard]] auto buildMove(const MotionRequest& request,
                               const moveit_msgs::msg::PlanningScene& scene,
                               bool include_live_stages = true) const
      -> std::unique_ptr<moveit::task_constructor::Task>;

 private:
  rclcpp::Node::SharedPtr node_;
  std::string planning_group_;
};

}  // namespace cellforge_motion
