#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/condition_node.h>

#include <cellforge_interfaces/action/execute_skill.hpp>
#include <chrono>
#include <memory>
#include <mutex>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>

namespace cellforge_supervisor {

inline constexpr auto kRosNodeBlackboardKey = "cellforge_ros_node";
using RosNodeWeakPtr = std::weak_ptr<rclcpp::Node>;

class CellReadyCondition : public BT::ConditionNode {
 public:
  CellReadyCondition(const std::string& name, const BT::NodeConfig& config);

  static auto providedPorts() -> BT::PortsList;

 private:
  auto tick() -> BT::NodeStatus override;
};

class ExecuteSkillAction : public BT::StatefulActionNode {
 public:
  using ExecuteSkill = cellforge_interfaces::action::ExecuteSkill;
  using GoalHandle = rclcpp_action::ClientGoalHandle<ExecuteSkill>;

  ExecuteSkillAction(const std::string& name, const BT::NodeConfig& config);

  static auto providedPorts() -> BT::PortsList;

 private:
  struct AsyncState {
    std::mutex mutex;
    GoalHandle::SharedPtr goal_handle;
    std::shared_ptr<const ExecuteSkill::Result> result;
    rclcpp_action::ResultCode result_code{rclcpp_action::ResultCode::UNKNOWN};
    bool goal_rejected{false};
    bool cancel_requested{false};
    bool cancel_sent{false};
  };

  auto onStart() -> BT::NodeStatus override;
  auto onRunning() -> BT::NodeStatus override;
  void onHalted() override;

  void requestCancellation(const std::shared_ptr<AsyncState>& state);
  void sendGoal();
  auto fail(const std::string& code, const std::string& message) -> BT::NodeStatus;

  rclcpp_action::Client<ExecuteSkill>::SharedPtr client_;
  std::shared_ptr<AsyncState> state_;
  ExecuteSkill::Goal pending_goal_;
  bool goal_sent_{false};
  std::chrono::steady_clock::time_point deadline_;
};

void registerSupervisorNodes(BT::BehaviorTreeFactory& factory);

auto newUuid() -> std::string;

}  // namespace cellforge_supervisor
