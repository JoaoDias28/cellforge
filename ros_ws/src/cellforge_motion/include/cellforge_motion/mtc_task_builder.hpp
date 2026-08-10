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
  std::unique_ptr<moveit::task_constructor::Task> build(const ManipulationRequest& request) const;

 private:
  rclcpp::Node::SharedPtr node_;
  std::string planning_group_;
};

}  // namespace cellforge_motion
