#include <exception>
#include <memory>
#include <rclcpp/rclcpp.hpp>

#include "cellforge_motion/motion_node.hpp"
#include "cellforge_motion/motion_service.hpp"
#include "cellforge_motion/moveit_planner.hpp"

auto main(int argc, char** argv) -> int {
  try {
    rclcpp::init(argc, argv);
    auto backend_node = std::make_shared<rclcpp::Node>(
        "motion_planner_backend",
        rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));
    const auto isaac_l2_direct = backend_node->get_parameter_or("isaac_l2_direct", false);
    auto planner = std::make_shared<cellforge_motion::MoveItPlanner>(backend_node, "manipulator",
                                                                     isaac_l2_direct);
    auto service = std::make_shared<cellforge_motion::MotionService>(planner);
    auto motion_node = std::make_shared<cellforge_motion::MotionNode>(service);
    rclcpp::executors::MultiThreadedExecutor executor;
    executor.add_node(backend_node);
    executor.add_node(motion_node);
    executor.spin();
    rclcpp::shutdown();
    return 0;
  } catch (const std::exception& error) {
    RCLCPP_FATAL(rclcpp::get_logger("cellforge_motion"), "Motion planner startup failed: %s",
                 error.what());
    if (rclcpp::ok()) {
      rclcpp::shutdown();
    }
    return 1;
  }
}
