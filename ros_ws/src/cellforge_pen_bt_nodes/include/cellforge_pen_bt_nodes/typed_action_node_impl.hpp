#pragma once

#include <builtin_interfaces/msg/duration.hpp>
#include <cstdint>

namespace cellforge_pen_bt_nodes {
namespace detail {
inline constexpr std::int64_t kDefaultTimeoutMilliseconds = 30000;
}

template <typename ActionT>
auto TypedActionNode<ActionT>::onStart() -> BT::NodeStatus {
  std::string action_name;
  std::int64_t timeout_ms = 0;
  if (!getInput("action_name", action_name) || !getInput("timeout_ms", timeout_ms) ||
      action_name.empty() || timeout_ms <= 0) {
    recordOutcome(config().blackboard, "pen.action.invalid_input",
                  "Typed ROS action requires an endpoint and positive timeout.");
    return BT::NodeStatus::FAILURE;
  }
  rclcpp::Node::SharedPtr node;
  try {
    node = config().blackboard->template get<RosNodeWeakPtr>(kRosNodeBlackboardKey).lock();
  } catch (const std::exception& error) {
    recordOutcome(config().blackboard, "pen.action.no_ros_node", error.what());
    return BT::NodeStatus::FAILURE;
  }
  if (!node) {
    recordOutcome(config().blackboard, "pen.action.no_ros_node",
                  "ROS node blackboard entry is unavailable.");
    return BT::NodeStatus::FAILURE;
  }
  const auto timeout = std::chrono::milliseconds(timeout_ms);
  client_ = rclcpp_action::create_client<ActionT>(node, action_name);
  state_ = std::make_shared<AsyncState>();
  try {
    pending_goal_ = buildGoal(newCommandId(), timeout);
  } catch (const std::exception& error) {
    recordOutcome(config().blackboard, "pen.action.invalid_input", error.what());
    return BT::NodeStatus::FAILURE;
  }
  deadline_ = std::chrono::steady_clock::now() + timeout;
  goal_sent_ = false;
  if (client_->action_server_is_ready()) {
    sendGoal();
  }
  return BT::NodeStatus::RUNNING;
}

template <typename ActionT>
void TypedActionNode<ActionT>::sendGoal() {
  auto state = state_;
  auto client = client_;
  typename rclcpp_action::Client<ActionT>::SendGoalOptions options;
  options.goal_response_callback = [state, client](const typename GoalHandle::SharedPtr& handle) {
    bool cancel_after_accept = false;
    {
      std::lock_guard lock(state->mutex);
      state->goal_handle = handle;
      state->goal_rejected = !handle;
      cancel_after_accept = handle && state->cancel_requested && !state->cancel_sent;
      state->cancel_sent = cancel_after_accept || state->cancel_sent;
    }
    if (cancel_after_accept) {
      (void)client->async_cancel_goal(handle);
    }
  };
  options.result_callback = [state](const typename GoalHandle::WrappedResult& wrapped) {
    std::lock_guard lock(state->mutex);
    state->result_code = wrapped.code;
    state->result = wrapped.result;
  };
  goal_sent_ = true;
  (void)client_->async_send_goal(pending_goal_, options);
}

template <typename ActionT>
auto TypedActionNode<ActionT>::onRunning() -> BT::NodeStatus {
  if (!state_) {
    recordOutcome(config().blackboard, "pen.action.internal",
                  "Typed action has no asynchronous state.");
    return BT::NodeStatus::FAILURE;
  }
  if (std::chrono::steady_clock::now() >= deadline_) {
    requestCancellation();
    return handleDeadline();
  }
  if (!goal_sent_) {
    if (client_ && client_->action_server_is_ready()) {
      sendGoal();
    }
    return BT::NodeStatus::RUNNING;
  }
  std::shared_ptr<const typename ActionT::Result> result;
  rclcpp_action::ResultCode result_code = rclcpp_action::ResultCode::UNKNOWN;
  bool rejected = false;
  {
    std::lock_guard lock(state_->mutex);
    result = state_->result;
    result_code = state_->result_code;
    rejected = state_->goal_rejected;
  }
  if (rejected) {
    recordOutcome(config().blackboard, "pen.action.rejected", "Typed action goal was rejected.");
    return BT::NodeStatus::FAILURE;
  }
  if (!result) {
    return BT::NodeStatus::RUNNING;
  }
  return handleResult(*result, result_code);
}

template <typename ActionT>
void TypedActionNode<ActionT>::onHalted() {
  requestCancellation();
}

template <typename ActionT>
void TypedActionNode<ActionT>::requestCancellation() {
  if (!state_) {
    return;
  }
  typename GoalHandle::SharedPtr handle;
  {
    std::lock_guard lock(state_->mutex);
    state_->cancel_requested = true;
    if (state_->goal_handle && !state_->cancel_sent) {
      state_->cancel_sent = true;
      handle = state_->goal_handle;
    }
  }
  if (handle && client_) {
    (void)client_->async_cancel_goal(handle);
  }
}

}  // namespace cellforge_pen_bt_nodes
