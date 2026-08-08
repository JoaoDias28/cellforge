#include <gtest/gtest.h>

#include <algorithm>
#include <atomic>
#include <cellforge_interfaces/action/execute_skill.hpp>
#include <cellforge_interfaces/action/run_job.hpp>
#include <cellforge_interfaces/msg/cell_state.hpp>
#include <cellforge_interfaces/msg/job_event.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <memory>
#include <mutex>
#include <rclcpp/executors/multi_threaded_executor.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_action/rclcpp_action.hpp>
#include <string>
#include <thread>
#include <vector>

#include "cellforge_supervisor/supervisor_node.hpp"

using namespace std::chrono_literals;

namespace cellforge_supervisor {
namespace {

using ExecuteSkill = cellforge_interfaces::action::ExecuteSkill;
using RunJob = cellforge_interfaces::action::RunJob;
using SkillGoalHandle = rclcpp_action::ServerGoalHandle<ExecuteSkill>;

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

class SupervisorNodeTest : public ::testing::Test {
 protected:
  static void SetUpTestSuite() {
    if (!rclcpp::ok()) {
      rclcpp::init(0, nullptr);
    }
  }

  static void TearDownTestSuite() { rclcpp::shutdown(); }
};

std::filesystem::path writeWorkflow() {
  const auto root = std::filesystem::temp_directory_path() / "cellforge-supervisor-test";
  std::filesystem::create_directories(root);
  std::ofstream output(root / "workflow@1.xml", std::ios::trunc);
  output << R"(<root BTCPP_format="4">
    <BehaviorTree ID="Main">
      <Sequence>
        <CellReady cell_ready="{cell_ready}"/>
        <ExecuteSkill action_name="/mock/execute_skill" skill_id="mock.nominal"
          execution_mode="{execution_mode}" input_payload_json="{input_payload_json}"
          timeout_ms="2000"/>
      </Sequence>
    </BehaviorTree>
  </root>)";
  output.close();
  return root;
}

RunJob::Goal makeJob(const std::string& job_id) {
  RunJob::Goal goal;
  goal.job_id = job_id;
  goal.cell_id = "test-cell";
  goal.recipe_id = "test.recipe";
  goal.recipe_version = 1;
  goal.task_id = "workflow@1";
  goal.input_payload_json = "{\"value\":1}";
  goal.execution_mode = "simulation";
  goal.idempotency_key = job_id;
  goal.timeout.sec = 3;
  return goal;
}

TEST_F(SupervisorNodeTest, RunJobSucceedsEmitsTransitionsAndReturnsDefinedCancellation) {
  const auto tree_root = writeWorkflow();
  rclcpp::NodeOptions options;
  options.append_parameter_override("tree_root", tree_root.string());
  options.append_parameter_override("cell_id", "test-cell");
  auto supervisor = std::make_shared<SupervisorNode>(options);
  auto harness = std::make_shared<rclcpp::Node>("supervisor_harness");

  std::atomic_int skill_accepted{0};
  std::atomic_bool hang_skill{false};
  std::atomic_bool skill_cancelled{false};
  std::vector<SkillGoalHandle::SharedPtr> held_skill_goals;
  auto skill_server = rclcpp_action::create_server<ExecuteSkill>(
      harness, "/mock/execute_skill",
      [](const rclcpp_action::GoalUUID&, std::shared_ptr<const ExecuteSkill::Goal>) {
        return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
      },
      [&skill_cancelled](const std::shared_ptr<SkillGoalHandle>) {
        skill_cancelled.store(true);
        return rclcpp_action::CancelResponse::ACCEPT;
      },
      [&skill_accepted, &hang_skill,
       &held_skill_goals](const std::shared_ptr<SkillGoalHandle> goal_handle) {
        ++skill_accepted;
        if (hang_skill.load()) {
          held_skill_goals.push_back(goal_handle);
          return;
        }
        auto result = std::make_shared<ExecuteSkill::Result>();
        result->success = true;
        result->result_code = "mock.completed";
        result->result_message = "Completed.";
        result->output_payload_json = "{}";
        goal_handle->succeed(result);
      });
  (void)skill_server;

  auto readiness_publisher =
      harness->create_publisher<cellforge_interfaces::msg::CellState>("/cell/state", 10);
  std::mutex events_mutex;
  std::vector<std::string> event_types;
  auto event_subscription = harness->create_subscription<cellforge_interfaces::msg::JobEvent>(
      "/events/job", 100,
      [&events_mutex, &event_types](const cellforge_interfaces::msg::JobEvent& event) {
        std::lock_guard lock(events_mutex);
        event_types.push_back(event.event_type);
      });
  (void)event_subscription;
  auto run_job_client = rclcpp_action::create_client<RunJob>(harness, "/cell/run_job");

  rclcpp::executors::MultiThreadedExecutor executor(rclcpp::ExecutorOptions(), 4);
  executor.add_node(supervisor);
  executor.add_node(harness);
  ExecutorThread spin(executor);
  ASSERT_TRUE(run_job_client->wait_for_action_server(2s));

  const auto discovery_deadline = std::chrono::steady_clock::now() + 2s;
  while (readiness_publisher->get_subscription_count() == 0 &&
         std::chrono::steady_clock::now() < discovery_deadline) {
    std::this_thread::sleep_for(5ms);
  }
  cellforge_interfaces::msg::CellState ready;
  ready.state = "READY";
  ready.safety_healthy = true;
  ready.all_required_devices_ready = true;
  readiness_publisher->publish(ready);
  std::this_thread::sleep_for(50ms);

  auto success_goal_future =
      run_job_client->async_send_goal(makeJob("11111111-1111-4111-8111-111111111111"));
  ASSERT_EQ(success_goal_future.wait_for(2s), std::future_status::ready);
  auto success_goal = success_goal_future.get();
  ASSERT_NE(success_goal, nullptr);
  auto success_result_future = run_job_client->async_get_result(success_goal);
  ASSERT_EQ(success_result_future.wait_for(3s), std::future_status::ready);
  const auto success_result = success_result_future.get();
  EXPECT_EQ(success_result.code, rclcpp_action::ResultCode::SUCCEEDED);
  ASSERT_NE(success_result.result, nullptr);
  EXPECT_TRUE(success_result.result->success);
  EXPECT_EQ(success_result.result->result_code, "supervisor.job.completed");
  const auto event_deadline = std::chrono::steady_clock::now() + 1s;
  bool transition_events_received = false;
  while (!transition_events_received && std::chrono::steady_clock::now() < event_deadline) {
    {
      std::lock_guard lock(events_mutex);
      transition_events_received = std::find(event_types.begin(), event_types.end(),
                                             "behavior_tree.node.entered") != event_types.end() &&
                                   std::find(event_types.begin(), event_types.end(),
                                             "behavior_tree.node.completed") != event_types.end() &&
                                   std::find(event_types.begin(), event_types.end(),
                                             "cell.state.changed") != event_types.end();
    }
    if (!transition_events_received) {
      std::this_thread::sleep_for(5ms);
    }
  }
  EXPECT_TRUE(transition_events_received);
  {
    std::lock_guard lock(events_mutex);
    EXPECT_NE(std::find(event_types.begin(), event_types.end(), "behavior_tree.node.entered"),
              event_types.end());
    EXPECT_NE(std::find(event_types.begin(), event_types.end(), "behavior_tree.node.completed"),
              event_types.end());
  }

  hang_skill.store(true);
  auto cancel_goal_future =
      run_job_client->async_send_goal(makeJob("22222222-2222-4222-8222-222222222222"));
  ASSERT_EQ(cancel_goal_future.wait_for(2s), std::future_status::ready);
  auto cancel_goal = cancel_goal_future.get();
  ASSERT_NE(cancel_goal, nullptr);
  const auto skill_deadline = std::chrono::steady_clock::now() + 2s;
  while (skill_accepted.load() < 2 && std::chrono::steady_clock::now() < skill_deadline) {
    std::this_thread::sleep_for(5ms);
  }
  ASSERT_EQ(skill_accepted.load(), 2);
  auto cancel_response = run_job_client->async_cancel_goal(cancel_goal);
  ASSERT_EQ(cancel_response.wait_for(2s), std::future_status::ready);
  auto cancel_result_future = run_job_client->async_get_result(cancel_goal);
  ASSERT_EQ(cancel_result_future.wait_for(3s), std::future_status::ready);
  const auto cancel_result = cancel_result_future.get();
  EXPECT_EQ(cancel_result.code, rclcpp_action::ResultCode::CANCELED);
  ASSERT_NE(cancel_result.result, nullptr);
  EXPECT_EQ(cancel_result.result->result_code, "supervisor.job.cancelled");
  const auto cancellation_deadline = std::chrono::steady_clock::now() + 1s;
  while (!skill_cancelled.load() && std::chrono::steady_clock::now() < cancellation_deadline) {
    std::this_thread::sleep_for(5ms);
  }
  EXPECT_TRUE(skill_cancelled.load());

  supervisor.reset();
  harness.reset();
  std::filesystem::remove_all(tree_root);
}

}  // namespace
}  // namespace cellforge_supervisor
