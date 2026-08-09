#include <memory>
#include <rclcpp/executors/multi_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>

#include "cellforge_supervisor/supervisor_node.hpp"

auto main(int argc, char* argv[]) -> int {
  rclcpp::init(argc, argv);
  auto supervisor = std::make_shared<cellforge_supervisor::SupervisorNode>();
  rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
  executor.add_node(supervisor);
  executor.spin();
  executor.remove_node(supervisor);
  supervisor.reset();
  rclcpp::shutdown();
  return 0;
}
