#include <memory>
#include <rclcpp/rclcpp.hpp>

#include "cellforge_motion/l0_planner.hpp"
#include "cellforge_motion/motion_node.hpp"
#include "cellforge_motion/motion_service.hpp"

auto main(int argc, char** argv) -> int {
  rclcpp::init(argc, argv);
  auto planner = std::make_shared<cellforge_motion::L0Planner>();
  auto service = std::make_shared<cellforge_motion::MotionService>(planner);
  auto node = std::make_shared<cellforge_motion::MotionNode>(service);
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(node);
  executor.spin();
  rclcpp::shutdown();
  return 0;
}
