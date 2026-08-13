#include <behaviortree_cpp/blackboard.h>
#include <gtest/gtest.h>

#include <cstdint>
#include <fstream>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <map>
#include <memory>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

#include "cellforge_supervisor/tree_validation.hpp"

namespace cellforge_pen_bt_nodes {
namespace {

using Json = nlohmann::json;

struct ScenarioScript {
  std::string id;
  std::vector<std::string> nodes;
  int process_commands{0};
  bool process_outcome_unknown{false};
};

auto portsFor(const std::string& node) -> BT::PortsList {
  if (node == "ValidateFrozenJob") {
    return {BT::InputPort<std::string>("job_id"),
            BT::InputPort<std::string>("cell_id"),
            BT::InputPort<std::string>("recipe_id"),
            BT::InputPort<std::uint32_t>("recipe_version"),
            BT::InputPort<std::string>("input_payload_json"),
            BT::InputPort<std::string>("execution_mode")};
  }
  if (node == "CheckSafetyHealthy") {
    return {BT::InputPort<bool>("healthy")};
  }
  if (node == "CheckRequiredDevicesReady") {
    return {BT::InputPort<bool>("ready")};
  }
  if (node == "LocateProduct") {
    return {BT::InputPort<std::string>("object_type"), BT::InputPort<std::string>("profile"),
            BT::OutputPort<geometry_msgs::msg::PoseStamped>("output_pose")};
  }
  if (node == "PickProduct") {
    return {BT::InputPort<geometry_msgs::msg::PoseStamped>("pose")};
  }
  if (node == "LoadFixture" || node == "VerifyFixture") {
    return {BT::InputPort<std::string>("fixture")};
  }
  if (node == "MoveRobotToProcessSafePose") {
    return {BT::InputPort<std::string>("pose")};
  }
  if (node == "SelectProcessProgram") {
    return {BT::InputPort<std::string>("program"), BT::InputPort<std::string>("variable_data")};
  }
  if (node == "ExecuteProcess") {
    return {BT::InputPort<std::string>("program"), BT::InputPort<std::string>("variable_data"),
            BT::InputPort<std::string>("recipe_id"),
            BT::InputPort<std::uint32_t>("recipe_version")};
  }
  if (node == "InspectProduct") {
    return {BT::InputPort<std::string>("profile"), BT::InputPort<std::string>("expected"),
            BT::OutputPort<std::string>("measurements")};
  }
  if (node == "RouteByInspection") {
    return {BT::InputPort<std::string>("inspection")};
  }
  return {};
}

auto scriptedTick(BT::TreeNode& node, const std::shared_ptr<ScenarioScript>& script)
    -> BT::NodeStatus {
  const auto name = node.registrationName();
  script->nodes.push_back(name);
  if (name == "CheckSafetyHealthy" && script->id == "pen-safety-unhealthy") {
    return BT::NodeStatus::FAILURE;
  }
  if (name == "LocateProduct") {
    if (script->id == "pen-no-pen" || script->id == "pen-pose-outside-limit") {
      return BT::NodeStatus::FAILURE;
    }
    geometry_msgs::msg::PoseStamped pose;
    pose.header.frame_id = "cell";
    pose.pose.orientation.w = 1.0;
    (void)node.setOutput("output_pose", pose);
  }
  if (name == "VerifyFixture" && script->id == "pen-fixture-not-seated") {
    return BT::NodeStatus::FAILURE;
  }
  if (name == "MoveRobotToProcessSafePose" && script->id == "pen-operator-cancel") {
    return BT::NodeStatus::FAILURE;
  }
  if (name == "ExecuteProcess") {
    ++script->process_commands;
    if (script->id == "pen-laser-not-ready" || script->id == "pen-laser-timeout") {
      return BT::NodeStatus::FAILURE;
    }
    if (script->id == "pen-process-outcome-unknown") {
      script->process_outcome_unknown = true;
      return BT::NodeStatus::FAILURE;
    }
  }
  if (name == "InspectProduct") {
    const bool accepted = script->id != "pen-inspection-text-mismatch";
    (void)node.setOutput("measurements", Json({{"accepted", accepted}}).dump());
    if (!accepted) {
      return BT::NodeStatus::FAILURE;
    }
  }
  return BT::NodeStatus::SUCCESS;
}

void configureFactory(BT::BehaviorTreeFactory& factory,
                      const std::shared_ptr<ScenarioScript>& script) {
  const std::array<const char*, 14> nodes{
      "ValidateFrozenJob",
      "CheckSafetyHealthy",
      "CheckRequiredDevicesReady",
      "LocateProduct",
      "PickProduct",
      "LoadFixture",
      "VerifyFixture",
      "MoveRobotToProcessSafePose",
      "SelectProcessProgram",
      "ExecuteProcess",
      "InspectProduct",
      "UnloadProduct",
      "RouteByInspection",
      "RecordProductionResult",
  };
  for (const auto* node : nodes) {
    factory.registerSimpleAction(
        node, [script](BT::TreeNode& tree_node) { return scriptedTick(tree_node, script); },
        portsFor(node));
  }
}

auto makeBlackboard(const std::shared_ptr<ScenarioScript>& script) -> BT::Blackboard::Ptr {
  auto blackboard = BT::Blackboard::create();
  blackboard->set("job_id", "8b67562f-b65c-43a6-a219-929cc5195001");
  blackboard->set("cell_id", "0d3c6b63-a57f-4207-8638-e4cf76efec90");
  blackboard->set("recipe_id", "pen-aluminium-reference");
  blackboard->set("recipe_version", std::uint32_t{1});
  blackboard->set("input_payload_json", std::string(R"({"engraving_text":"CELLFORGE"})"));
  blackboard->set("execution_mode", "simulation");
  blackboard->set("cell_ready", script->id != "pen-safety-unhealthy");
  return blackboard;
}

auto finalStatus(const ScenarioScript& script, BT::NodeStatus status) -> std::string {
  if (script.id == "pen-operator-cancel") {
    return "CANCELLED";
  }
  if (script.id == "pen-safety-unhealthy") {
    return "REJECTED";
  }
  if (script.id == "pen-process-outcome-unknown") {
    return "OUTCOME_UNKNOWN";
  }
  return status == BT::NodeStatus::SUCCESS ? "SUCCESS" : "RECOVERABLE_FAULT";
}

TEST(PenScenarios, CanonicalRuntimeTraceMatchesOracleForAllTenScenarios) {
  std::ifstream input(PEN_TRACE_EXPECTATIONS_PATH);
  ASSERT_TRUE(input.good());
  const auto expectations = Json::parse(input);
  ASSERT_EQ(expectations.size(), 10U);
  for (const auto& [scenario_id, expected] : expectations.items()) {
    auto script = std::make_shared<ScenarioScript>();
    script->id = scenario_id;
    BT::BehaviorTreeFactory factory;
    configureFactory(factory, script);
    auto tree = cellforge_supervisor::createValidatedTreeFromFile(factory, PEN_TREE_PATH,
                                                                  makeBlackboard(script));
    const auto status = tree.tickWhileRunning();
    EXPECT_EQ(finalStatus(*script, status), expected.at("final_status").get<std::string>())
        << scenario_id;
    EXPECT_EQ(script->nodes, expected.at("nodes").get<std::vector<std::string>>()) << scenario_id;
    if (scenario_id == "pen-safety-unhealthy") {
      EXPECT_EQ(script->process_commands, 0);
    }
    if (scenario_id == "pen-process-outcome-unknown") {
      EXPECT_EQ(script->process_commands, 1);
      EXPECT_TRUE(script->process_outcome_unknown);
    }
  }
}

}  // namespace
}  // namespace cellforge_pen_bt_nodes
