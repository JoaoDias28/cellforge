#include <memory>
#include <rclcpp/rclcpp.hpp>

#include "cellforge_motion/motion_node.hpp"
#include "cellforge_motion/motion_service.hpp"
#include "cellforge_motion/moveit_planner.hpp"

auto main(int argc, char** argv) -> int {
  rclcpp::init(argc, argv);
  auto backend_node = std::make_shared<rclcpp::Node>(
      "motion_planner_backend",
      rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
  auto planner = std::make_shared<cellforge_motion::MoveItPlanner>(backend_node);
  auto service = std::make_shared<cellforge_motion::MotionService>(planner);
  auto motion_node = std::make_shared<cellforge_motion::MotionNode>(service);
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(backend_node);
  executor.add_node(motion_node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}
