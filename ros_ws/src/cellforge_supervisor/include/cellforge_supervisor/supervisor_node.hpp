#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/tree_node.h>

#include <atomic>
#include <cellforge_interfaces/action/run_job.hpp>
#include <cellforge_interfaces/msg/cell_state.hpp>
#include <cellforge_interfaces/msg/job_event.hpp>
#include <chrono>
#include <filesystem>
#include <memory>
#include <mutex>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <stop_token>
#include <string>
#include <thread>
#include <vector>

namespace cellforge_supervisor {

class SupervisorNode : public rclcpp::Node {
 public:
  using RunJob = cellforge_interfaces::action::RunJob;
  using GoalHandleRunJob = rclcpp_action::ServerGoalHandle<RunJob>;

  explicit SupervisorNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());
  ~SupervisorNode() override;

 private:
  rclcpp_action::GoalResponse handleGoal(const rclcpp_action::GoalUUID& uuid,
                                         std::shared_ptr<const RunJob::Goal> goal);
  rclcpp_action::CancelResponse handleCancel(const std::shared_ptr<GoalHandleRunJob> goal_handle);
  void handleAccepted(const std::shared_ptr<GoalHandleRunJob> goal_handle);
  void executeGoal(const std::shared_ptr<GoalHandleRunJob>& goal_handle,
                   std::stop_token stop_token);
  void finishGoalSlot();

  void onCellState(const cellforge_interfaces::msg::CellState& message);
  void transitionState(const std::string& state, const std::string& job_id = {},
                       const std::string& trace_id = {});
  void publishEvent(const std::string& event_type, const std::string& job_id,
                    const std::string& trace_id, const std::string& payload_json,
                    const std::string& command_id = {}, const std::string& severity = "INFO");
  std::vector<BT::TreeNode::StatusChangeSubscriber> attachTransitionEvents(
      BT::Tree& tree, const std::string& job_id, const std::string& trace_id);
  void publishFeedback(const std::shared_ptr<GoalHandleRunJob>& goal_handle,
                       const std::string& state, const std::string& active_node,
                       const std::string& message);

  BT::BehaviorTreeFactory factory_;
  std::filesystem::path tree_root_;
  std::string cell_id_;
  std::string bundle_id_;
  std::chrono::milliseconds default_job_timeout_{300000};
  std::atomic_bool job_active_{false};
  std::atomic_bool cancel_requested_{false};
  std::atomic_bool cell_ready_{false};
  std::atomic_bool safety_healthy_{false};
  std::atomic_bool required_devices_ready_{false};
  std::mutex state_mutex_;
  std::string state_{"IDLE"};
  std::jthread worker_;

  rclcpp_action::Server<RunJob>::SharedPtr run_job_server_;
  rclcpp::Publisher<cellforge_interfaces::msg::CellState>::SharedPtr state_publisher_;
  rclcpp::Publisher<cellforge_interfaces::msg::JobEvent>::SharedPtr event_publisher_;
  rclcpp::Subscription<cellforge_interfaces::msg::CellState>::SharedPtr cell_state_subscription_;
};

}  // namespace cellforge_supervisor
