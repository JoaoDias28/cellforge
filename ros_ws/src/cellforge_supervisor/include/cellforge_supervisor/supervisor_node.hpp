#pragma once

#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/tree_node.h>

#include <atomic>
#include <cellforge_interfaces/action/execute_frozen_job.hpp>
#include <cellforge_interfaces/msg/cell_state.hpp>
#include <cellforge_interfaces/msg/job_event.hpp>
#include <chrono>
#include <condition_variable>
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
  using ExecuteFrozenJob = cellforge_interfaces::action::ExecuteFrozenJob;
  using GoalHandleFrozenJob = rclcpp_action::ServerGoalHandle<ExecuteFrozenJob>;

  explicit SupervisorNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());
  ~SupervisorNode() override;

 private:
  auto handleGoal(const rclcpp_action::GoalUUID& uuid,
                  const std::shared_ptr<const ExecuteFrozenJob::Goal>& goal)
      -> rclcpp_action::GoalResponse;
  auto handleCancel(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle)
      -> rclcpp_action::CancelResponse;
  void handleAccepted(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle);
  void workerLoop(const std::stop_token& stop_token);
  void executeGoal(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle,
                   const std::stop_token& stop_token);
  void finishGoalSlot();

  void onCellState(const cellforge_interfaces::msg::CellState& message);
  void transitionState(const std::string& state, const std::string& job_id = {},
                       const std::string& trace_id = {});
  void publishEvent(const std::string& event_type, const std::string& job_id,
                    const std::string& trace_id, const std::string& payload_json,
                    const std::string& command_id = {}, const std::string& severity = "INFO");
  auto attachTransitionEvents(BT::Tree& tree, const std::string& job_id,
                              const std::string& trace_id)
      -> std::vector<BT::TreeNode::StatusChangeSubscriber>;
  static void publishFeedback(const std::shared_ptr<GoalHandleFrozenJob>& goal_handle,
                              const std::string& state, const std::string& active_node,
                              const std::string& message);

  BT::BehaviorTreeFactory factory_;
  std::filesystem::path tree_root_;
  std::string cell_id_;
  std::string bundle_id_;
  static constexpr std::chrono::milliseconds kDefaultJobTimeout{300000};
  std::chrono::milliseconds default_job_timeout_{kDefaultJobTimeout};
  std::atomic_bool job_active_{false};
  std::atomic_bool cancel_requested_{false};
  std::atomic_bool cell_ready_{false};
  std::atomic_bool safety_healthy_{false};
  std::atomic_bool required_devices_ready_{false};
  std::mutex state_mutex_;
  std::string state_{"IDLE"};
  std::mutex worker_mutex_;
  std::condition_variable_any worker_condition_;
  std::shared_ptr<GoalHandleFrozenJob> pending_goal_handle_;
  std::shared_ptr<const ExecuteFrozenJob::Goal> current_identity_;
  std::jthread worker_;

  rclcpp_action::Server<ExecuteFrozenJob>::SharedPtr run_job_server_;
  rclcpp::Publisher<cellforge_interfaces::msg::CellState>::SharedPtr state_publisher_;
  rclcpp::Publisher<cellforge_interfaces::msg::JobEvent>::SharedPtr event_publisher_;
  rclcpp::Subscription<cellforge_interfaces::msg::CellState>::SharedPtr cell_state_subscription_;
};

}  // namespace cellforge_supervisor
