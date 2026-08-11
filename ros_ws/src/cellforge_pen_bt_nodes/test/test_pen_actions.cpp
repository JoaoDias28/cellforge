#include <behaviortree_cpp/blackboard.h>
#include <gtest/gtest.h>

#include <atomic>
#include <cellforge_interfaces/action/execute_process.hpp>
#include <chrono>
#include <memory>
#include <rclcpp/executors/multi_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>
#include <thread>
#include <vector>

#include "cellforge_pen_bt_nodes/pen_nodes.hpp"

using namespace std::chrono_literals;

namespace cellforge_pen_bt_nodes {
namespace {

using Process = cellforge_interfaces::action::ExecuteProcess;
using ProcessHandle = rclcpp_action::ServerGoalHandle<Process>;

enum class ProcessOutcome { SUCCESS, UNKNOWN, HANG };

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

class PenActionsTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }
  static void TearDownTestSuite() { rclcpp::shutdown(); }
};

auto makeProcessServer(const rclcpp::Node::SharedPtr& node, const std::string& endpoint,
                       ProcessOutcome outcome, std::atomic_int& accepted,
                       std::atomic_bool& cancelled) -> rclcpp_action::Server<Process>::SharedPtr {
  auto held = std::make_shared<std::vector<std::shared_ptr<ProcessHandle>>>();
  return rclcpp_action::create_server<Process>(
      node, endpoint,
      [](const rclcpp_action::GoalUUID&, const std::shared_ptr<const Process::Goal>& goal) {
        return goal->program_id == "ALU_REFERENCE_01"
                   ? rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE
                   : rclcpp_action::GoalResponse::REJECT;
      },
      [&cancelled](const std::shared_ptr<ProcessHandle>) {
        cancelled.store(true);
        return rclcpp_action::CancelResponse::ACCEPT;
      },
      [outcome, &accepted, held](const std::shared_ptr<ProcessHandle> handle) {
        ++accepted;
        if (outcome == ProcessOutcome::HANG) {
          held->push_back(handle);
          return;
        }
        auto result = std::make_shared<Process::Result>();
        result->outcome_certain = outcome == ProcessOutcome::SUCCESS;
        result->success = outcome == ProcessOutcome::SUCCESS;
        result->result_code =
            result->success ? "process.completed" : "laser.process.outcome_unknown";
        result->result_message = result->success ? "Completed." : "Communication was lost.";
        result->process_data_json = "{}";
        if (result->success) {
          handle->succeed(result);
        } else {
          handle->abort(result);
        }
      });
}

auto makeProcessTree(const rclcpp::Node::SharedPtr& node, const std::string& endpoint,
                     std::int64_t timeout_ms) -> BT::Tree {
  BT::BehaviorTreeFactory factory;
  registerPenNodes(factory);
  auto blackboard = BT::Blackboard::create();
  blackboard->set<RosNodeWeakPtr>(kRosNodeBlackboardKey, RosNodeWeakPtr{node});
  blackboard->set("trace_id", "1f0ea290-1442-4c2f-9ce8-d66fef78c949");
  blackboard->set("recipe_id", "pen-aluminium-reference");
  blackboard->set("recipe_version", std::uint32_t{1});
  blackboard->set("input_payload_json", std::string(R"({"engraving_text":"TEST"})"));
  const auto xml =
      "<root BTCPP_format=\"4\"><BehaviorTree ID=\"Main\"><ExecuteProcess "
      "program=\"ALU_REFERENCE_01\" variable_data=\"{input_payload_json}\" "
      "recipe_id=\"{recipe_id}\" recipe_version=\"{recipe_version}\" action_name=\"" +
      endpoint + "\" timeout_ms=\"" + std::to_string(timeout_ms) + "\"/></BehaviorTree></root>";
  return factory.createTreeFromText(xml, blackboard);
}

auto tickUntilTerminal(BT::Tree& tree, std::chrono::milliseconds timeout) -> BT::NodeStatus {
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  auto status = BT::NodeStatus::IDLE;
  while (std::chrono::steady_clock::now() < deadline) {
    status = tree.tickOnce();
    if (status == BT::NodeStatus::SUCCESS || status == BT::NodeStatus::FAILURE) {
      return status;
    }
    std::this_thread::sleep_for(2ms);
  }
  return status;
}

TEST_F(PenActionsTest, TypedProcessSuccessCompletes) {
  auto server_node = std::make_shared<rclcpp::Node>("pen_process_success_server");
  auto client_node = std::make_shared<rclcpp::Node>("pen_process_success_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeProcessServer(server_node, "/test/process_success", ProcessOutcome::SUCCESS,
                                  accepted, cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);
  auto tree = makeProcessTree(client_node, "/test/process_success", 1000);
  EXPECT_EQ(tickUntilTerminal(tree, 2s), BT::NodeStatus::SUCCESS);
  EXPECT_EQ(accepted.load(), 1);
}

TEST_F(PenActionsTest, UncertainProcessStopsAfterExactlyOneCommand) {
  auto server_node = std::make_shared<rclcpp::Node>("pen_process_unknown_server");
  auto client_node = std::make_shared<rclcpp::Node>("pen_process_unknown_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeProcessServer(server_node, "/test/process_unknown", ProcessOutcome::UNKNOWN,
                                  accepted, cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);
  auto tree = makeProcessTree(client_node, "/test/process_unknown", 1000);
  EXPECT_EQ(tickUntilTerminal(tree, 2s), BT::NodeStatus::FAILURE);
  EXPECT_EQ(accepted.load(), 1);
  EXPECT_TRUE(tree.rootBlackboard()->get<bool>("process_outcome_unknown"));
  EXPECT_FALSE(tree.rootBlackboard()->get<bool>("last_outcome_certain"));
}

TEST_F(PenActionsTest, HaltAndDeadlineRequestCancellationAndPreserveUncertainty) {
  auto server_node = std::make_shared<rclcpp::Node>("pen_process_hang_server");
  auto client_node = std::make_shared<rclcpp::Node>("pen_process_hang_client");
  std::atomic_int accepted{0};
  std::atomic_bool cancelled{false};
  auto server = makeProcessServer(server_node, "/test/process_hang", ProcessOutcome::HANG, accepted,
                                  cancelled);
  (void)server;
  rclcpp::executors::MultiThreadedExecutor executor;
  executor.add_node(server_node);
  executor.add_node(client_node);
  ExecutorThread spin(executor);

  auto cancelled_tree = makeProcessTree(client_node, "/test/process_hang", 1000);
  ASSERT_EQ(tickUntilTerminal(cancelled_tree, 100ms), BT::NodeStatus::RUNNING);
  cancelled_tree.haltTree();
  const auto cancel_deadline = std::chrono::steady_clock::now() + 1s;
  while (!cancelled.load() && std::chrono::steady_clock::now() < cancel_deadline) {
    std::this_thread::sleep_for(2ms);
  }
  EXPECT_TRUE(cancelled.load());

  cancelled.store(false);
  auto timed_tree = makeProcessTree(client_node, "/test/process_hang", 50);
  EXPECT_EQ(tickUntilTerminal(timed_tree, 1s), BT::NodeStatus::FAILURE);
  EXPECT_TRUE(timed_tree.rootBlackboard()->get<bool>("process_outcome_unknown"));
  EXPECT_FALSE(timed_tree.rootBlackboard()->get<bool>("last_outcome_certain"));
}

}  // namespace
}  // namespace cellforge_pen_bt_nodes
