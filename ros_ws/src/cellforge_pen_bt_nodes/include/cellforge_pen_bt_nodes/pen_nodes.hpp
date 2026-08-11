#pragma once

#include <behaviortree_cpp/action_node.h>
#include <behaviortree_cpp/bt_factory.h>
#include <behaviortree_cpp/condition_node.h>

#include <cellforge_interfaces/action/execute_manipulation.hpp>
#include <cellforge_interfaces/action/execute_process.hpp>
#include <cellforge_interfaces/action/execute_skill.hpp>
#include <cellforge_interfaces/action/inspect_object.hpp>
#include <cellforge_interfaces/action/locate_object.hpp>
#include <cellforge_interfaces/action/move_to_pose.hpp>
#include <chrono>
#include <memory>
#include <mutex>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>

namespace cellforge_pen_bt_nodes {

inline constexpr auto kRosNodeBlackboardKey = "cellforge_ros_node";
using RosNodeWeakPtr = std::weak_ptr<rclcpp::Node>;

void recordOutcome(const BT::Blackboard::Ptr& blackboard, const std::string& code,
                   const std::string& message, bool outcome_certain = true);

template <typename ActionT>
class TypedActionNode : public BT::StatefulActionNode {
 public:
  using GoalHandle = rclcpp_action::ClientGoalHandle<ActionT>;

  TypedActionNode(const std::string& name, const BT::NodeConfig& config)
      : BT::StatefulActionNode(name, config) {}

 protected:
  struct AsyncState {
    std::mutex mutex;
    typename GoalHandle::SharedPtr goal_handle;
    std::shared_ptr<const typename ActionT::Result> result;
    rclcpp_action::ResultCode result_code{rclcpp_action::ResultCode::UNKNOWN};
    bool goal_rejected{false};
    bool cancel_requested{false};
    bool cancel_sent{false};
  };

  virtual auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout) ->
      typename ActionT::Goal = 0;
  virtual auto handleResult(const typename ActionT::Result& result,
                            rclcpp_action::ResultCode result_code) -> BT::NodeStatus = 0;
  virtual auto handleDeadline() -> BT::NodeStatus {
    recordOutcome(config().blackboard, "pen.action.timeout",
                  "Typed ROS action exceeded its steady deadline; cancellation was requested.");
    return BT::NodeStatus::FAILURE;
  }

  auto onStart() -> BT::NodeStatus override;
  auto onRunning() -> BT::NodeStatus override;
  void onHalted() override;

 private:
  void sendGoal();
  void requestCancellation();

  rclcpp_action::Client<ActionT>::SharedPtr client_;
  std::shared_ptr<AsyncState> state_;
  typename ActionT::Goal pending_goal_;
  std::chrono::steady_clock::time_point deadline_;
  bool goal_sent_{false};
};

class ValidateFrozenJob : public BT::ConditionNode {
 public:
  ValidateFrozenJob(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
  auto tick() -> BT::NodeStatus override;
};

class CheckSafetyHealthy : public BT::ConditionNode {
 public:
  CheckSafetyHealthy(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
  auto tick() -> BT::NodeStatus override;
};

class CheckRequiredDevicesReady : public BT::ConditionNode {
 public:
  CheckRequiredDevicesReady(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
  auto tick() -> BT::NodeStatus override;
};

class LocateProduct : public TypedActionNode<cellforge_interfaces::action::LocateObject> {
 public:
  using TypedActionNode::TypedActionNode;
  static auto providedPorts() -> BT::PortsList;

 protected:
  auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
      -> cellforge_interfaces::action::LocateObject::Goal override;
  auto handleResult(const cellforge_interfaces::action::LocateObject::Result& result,
                    rclcpp_action::ResultCode result_code) -> BT::NodeStatus override;
};

class ManipulateProduct
    : public TypedActionNode<cellforge_interfaces::action::ExecuteManipulation> {
 public:
  ManipulateProduct(const std::string& name, const BT::NodeConfig& config, std::string operation);
  static auto commonPorts() -> BT::PortsList;

 protected:
  auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
      -> cellforge_interfaces::action::ExecuteManipulation::Goal override;
  auto handleResult(const cellforge_interfaces::action::ExecuteManipulation::Result& result,
                    rclcpp_action::ResultCode result_code) -> BT::NodeStatus override;

 private:
  std::string operation_;
};

class PickProduct final : public ManipulateProduct {
 public:
  PickProduct(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
};

class LoadFixture final : public ManipulateProduct {
 public:
  LoadFixture(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
};

class UnloadProduct final : public ManipulateProduct {
 public:
  UnloadProduct(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
};

class MoveRobotToProcessSafePose
    : public TypedActionNode<cellforge_interfaces::action::MoveToPose> {
 public:
  using TypedActionNode::TypedActionNode;
  static auto providedPorts() -> BT::PortsList;

 protected:
  auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
      -> cellforge_interfaces::action::MoveToPose::Goal override;
  auto handleResult(const cellforge_interfaces::action::MoveToPose::Result& result,
                    rclcpp_action::ResultCode result_code) -> BT::NodeStatus override;
};

class ExecuteSkillLeaf : public TypedActionNode<cellforge_interfaces::action::ExecuteSkill> {
 public:
  ExecuteSkillLeaf(const std::string& name, const BT::NodeConfig& config, std::string skill_id);
  static auto commonPorts() -> BT::PortsList;

 protected:
  auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
      -> cellforge_interfaces::action::ExecuteSkill::Goal override;
  auto handleResult(const cellforge_interfaces::action::ExecuteSkill::Result& result,
                    rclcpp_action::ResultCode result_code) -> BT::NodeStatus override;
  virtual auto inputPayload() -> std::string = 0;

 private:
  std::string skill_id_;
};

class VerifyFixture final : public ExecuteSkillLeaf {
 public:
  VerifyFixture(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;

 protected:
  auto inputPayload() -> std::string override;
};

class SelectProcessProgram final : public ExecuteSkillLeaf {
 public:
  SelectProcessProgram(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;

 protected:
  auto inputPayload() -> std::string override;
};

class ExecuteProcess : public TypedActionNode<cellforge_interfaces::action::ExecuteProcess> {
 public:
  using TypedActionNode::TypedActionNode;
  static auto providedPorts() -> BT::PortsList;

 protected:
  auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
      -> cellforge_interfaces::action::ExecuteProcess::Goal override;
  auto handleResult(const cellforge_interfaces::action::ExecuteProcess::Result& result,
                    rclcpp_action::ResultCode result_code) -> BT::NodeStatus override;
  auto handleDeadline() -> BT::NodeStatus override;
};

class InspectProduct : public TypedActionNode<cellforge_interfaces::action::InspectObject> {
 public:
  using TypedActionNode::TypedActionNode;
  static auto providedPorts() -> BT::PortsList;

 protected:
  auto buildGoal(const std::string& command_id, std::chrono::milliseconds timeout)
      -> cellforge_interfaces::action::InspectObject::Goal override;
  auto handleResult(const cellforge_interfaces::action::InspectObject::Result& result,
                    rclcpp_action::ResultCode result_code) -> BT::NodeStatus override;
};

class RouteByInspection : public BT::ConditionNode {
 public:
  RouteByInspection(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
  auto tick() -> BT::NodeStatus override;
};

class RecordProductionResult : public BT::SyncActionNode {
 public:
  RecordProductionResult(const std::string& name, const BT::NodeConfig& config);
  static auto providedPorts() -> BT::PortsList;
  auto tick() -> BT::NodeStatus override;
};

void registerPenNodes(BT::BehaviorTreeFactory& factory);
auto newCommandId() -> std::string;

}  // namespace cellforge_pen_bt_nodes

#include "cellforge_pen_bt_nodes/typed_action_node_impl.hpp"
