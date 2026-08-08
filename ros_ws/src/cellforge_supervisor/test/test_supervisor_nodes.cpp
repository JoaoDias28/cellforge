#include <behaviortree_cpp/blackboard.h>
#include <gtest/gtest.h>

#include <atomic>
#include <cellforge_interfaces/action/execute_skill.hpp>
#include <chrono>
#include <memory>
#include <rclcpp/executors/multi_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>
#include <thread>

#include "cellforge_supervisor/supervisor_nodes.hpp"
#include "cellforge_supervisor/tree_validation.hpp"

using namespace std::chrono_literals;

namespace cellforge_supervisor {
namespace {

using ExecuteSkill = cellforge_interfaces::action::ExecuteSkill;
using ServerGoalHandle = rclcpp_action::ServerGoalHandle<ExecuteSkill>;

enum class MockOutcome {
  SUCCESS,
  HANG,
  FAIL_ONCE,
};

class ExecutorThread {
 public:
  explicit ExecutorThread(rclcpp::executors::MultiThreadedExecutor& executor)
      : executor_(executor), thread_([this]() { executor_.spin(); }) {}

  ~ExecutorThread() {
    executor_.cancel();
    thread_.join();
  }

 private:
  rclcpp::executors::MultiThreadedExecutor& executor_;
  std::jthread thread_;
};

class SupervisorNodesTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  static void TearDownTestSuite() { rclcpp::shutdown(); }
};

BT::Tree makeSkillTree(const rclcpp::Node::SharedPtr& client_node, const std::string& action_name,
                       std::int64_t timeout_ms, bool retry) {
  BT::BehaviorTreeFactory factory;
  registerSupervisorNodes(factory);
  auto blackboard = BT::Blackboard::create();
  blackboard->set<rclcpp::Node::SharedPtr>(kRosNodeBlackboardKey, client_node);

  const auto action = "<ExecuteSkill action_name=\"" + action_name +
                      "\" skill_id=\"mock.skill\" execution_mode=\"simulation\" timeout_ms=\"" +
                      std::to_string(timeout_ms) + "\"/>";
  const auto body =
      retry ? "<RetryUntilSuccessful num_attempts=\"2\">" + action + "</RetryUntilSuccessful>"
            : action;
  const auto xml =
      "<root BTCPP_format=\"4\"><BehaviorTree ID=\"Main\">" + body + "</BehaviorTree></root>";
  return createValidatedTreeFromText(factory, xml, blackboard);
}

rclcpp_action::Server<ExecuteSkill>::SharedPtr makeServer(const rclcpp::Node::SharedPtr& node,
                                                          const std::string& action_name,
                                                          MockOutcome outcome,
                                                          std::atomic_int& accepted,
                                                          std::atomic_bool& cancelled) {
  return rclcpp_action::create_server<ExecuteSkill>(
      node, action_name,
      [](const rclcpp_action::GoalUUID&, std::shared_ptr<const ExecuteSkill::Goal>) {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      },
      [&cancelled](const std::shared_ptr<ServerGoalHandle>) {
        cancelled.store(true);
        return rclcpp_action::CancelResponse::ACCEPT;
      },
      [&accepted, outcome](const std::shared_ptr<ServerGoalHandle> goal_handle) {
        const int attempt = ++accepted;
        if (outcome == MockOutcome::HANG) {
          return;
        }
        auto result = std::make_shared<ExecuteSkill::Result>();
        if (outcome == MockOutcome::FAIL_ONCE && attempt == 1) {
          result->success = false;
          result->result_code = "mock.injected_failure";
          result->result_message = "Retry me.";
          result->output_payload_json = "{}";
          goal_handle->abort(result);
          return;
        }
        result->success = true;
        result->result_code = "mock.completed";
        result->result_message = "Completed.";
        result->output_payload_json = "{\"ok\":true}";
        goal_handle->succeed(result);
      });
}

BT::NodeStatus tickUntilTerminal(BT::Tree& tree, std::chrono::milliseconds timeout) {
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  BT::NodeStatus status = BT::NodeStatus::IDLE;
  while (std::chrono::steady_clock::now() < deadline) {
    status = tree.tickOnce();
    if (status == BT::NodeStatus::SUCCESS || status == BT::NodeStatus::FAILURE) {
      return status;
    }
    std::this_thread::sleep_for(2ms);
  }
  return status;
}

TEST_F(SupervisorNodesTest, SimpleMockWorkflowSucceedsWithoutBlockingTickThread) {
  auto server_node = std::make_shared<rclcpp::Node>("success_server");
  auto client_node = std::make_shared<rclcpp::Node>("success_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeServer(server_node, "/test/success", MockOutcome::SUCCESS, accepted, cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);

  auto tree = makeSkillTree(client_node, "/test/success", 1000, false);
  const auto started = std::chrono::steady_clock::now();
  const auto first_status = tree.tickOnce();
  const auto first_tick_duration = std::chrono::steady_clock::now() - started;
  EXPECT_EQ(first_status, BT::NodeStatus::RUNNING);
  EXPECT_LT(first_tick_duration, 50ms);
  EXPECT_EQ(tickUntilTerminal(tree, 2s), BT::NodeStatus::SUCCESS);
  EXPECT_EQ(accepted.load(), 1);
}

TEST_F(SupervisorNodesTest, RetryDecoratorResubmitsAfterDefinedFailure) {
  auto server_node = std::make_shared<rclcpp::Node>("retry_server");
  auto client_node = std::make_shared<rclcpp::Node>("retry_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeServer(server_node, "/test/retry", MockOutcome::FAIL_ONCE, accepted, cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);

  auto tree = makeSkillTree(client_node, "/test/retry", 1000, true);
  EXPECT_EQ(tickUntilTerminal(tree, 2s), BT::NodeStatus::SUCCESS);
  EXPECT_EQ(accepted.load(), 2);
}

TEST_F(SupervisorNodesTest, HaltPropagatesCancellationToActiveAction) {
  auto server_node = std::make_shared<rclcpp::Node>("cancel_server");
  auto client_node = std::make_shared<rclcpp::Node>("cancel_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeServer(server_node, "/test/cancel", MockOutcome::HANG, accepted, cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);

  auto tree = makeSkillTree(client_node, "/test/cancel", 1000, false);
  ASSERT_EQ(tickUntilTerminal(tree, 200ms), BT::NodeStatus::RUNNING);
  ASSERT_EQ(accepted.load(), 1);
  tree.haltTree();
  const auto deadline = std::chrono::steady_clock::now() + 1s;
  while (!cancelled.load() && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(2ms);
  }
  EXPECT_TRUE(cancelled.load());
}

TEST_F(SupervisorNodesTest, TimeoutReturnsDefinedFailureAndRequestsCancellation) {
  auto server_node = std::make_shared<rclcpp::Node>("timeout_server");
  auto client_node = std::make_shared<rclcpp::Node>("timeout_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeServer(server_node, "/test/timeout", MockOutcome::HANG, accepted, cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);

  auto tree = makeSkillTree(client_node, "/test/timeout", 50, false);
  EXPECT_EQ(tickUntilTerminal(tree, 1s), BT::NodeStatus::FAILURE);
  const auto deadline = std::chrono::steady_clock::now() + 1s;
  while (!cancelled.load() && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(2ms);
  }
  EXPECT_TRUE(cancelled.load());
}

}  // namespace
}  // namespace cellforge_supervisor
