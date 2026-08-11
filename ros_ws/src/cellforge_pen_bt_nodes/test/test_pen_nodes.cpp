#include <behaviortree_cpp/blackboard.h>
#include <gtest/gtest.h>

#include <string>

#include "cellforge_pen_bt_nodes/pen_nodes.hpp"

namespace cellforge_pen_bt_nodes {
namespace {

TEST(PenNodes, RegistersEveryCanonicalLeaf) {
  BT::BehaviorTreeFactory factory;
  registerPenNodes(factory);
  const std::array<const char*, 14> expected{
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
  for (const auto* node : expected) {
    EXPECT_TRUE(factory.manifests().contains(node)) << node;
  }
}

TEST(PenNodes, PureLeavesValidateRefuseRouteAndRecordDeterministically) {
  BT::BehaviorTreeFactory factory;
  registerPenNodes(factory);
  auto blackboard = BT::Blackboard::create();
  blackboard->set("job_id", "8b67562f-b65c-43a6-a219-929cc5195001");
  blackboard->set("cell_id", "0d3c6b63-a57f-4207-8638-e4cf76efec90");
  blackboard->set("recipe_id", "pen-aluminium-reference");
  blackboard->set("recipe_version", std::uint32_t{1});
  blackboard->set("input_payload_json", std::string(R"({"engraving_text":"CELLFORGE"})"));
  blackboard->set("execution_mode", "simulation");
  blackboard->set("cell_ready", true);
  blackboard->set("inspection", std::string(R"({"accepted":true})"));
  const std::string xml = R"(
    <root BTCPP_format="4"><BehaviorTree ID="Main"><Sequence>
      <ValidateFrozenJob job_id="{job_id}" cell_id="{cell_id}" recipe_id="{recipe_id}"
        recipe_version="{recipe_version}" input_payload_json="{input_payload_json}"
        execution_mode="{execution_mode}"/>
      <CheckSafetyHealthy healthy="{cell_ready}"/>
      <CheckRequiredDevicesReady ready="{cell_ready}"/>
      <RouteByInspection inspection="{inspection}"/>
      <RecordProductionResult/>
    </Sequence></BehaviorTree></root>)";
  auto tree = factory.createTreeFromText(xml, blackboard);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::SUCCESS);
  EXPECT_TRUE(blackboard->get<bool>("production_result_recorded"));

  blackboard->set("cell_ready", false);
  tree = factory.createTreeFromText(xml, blackboard);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::FAILURE);
  EXPECT_EQ(blackboard->get<std::string>("last_result_code"), "safety.unhealthy");
}

TEST(PenNodes, InvalidFrozenPayloadFailsClosed) {
  BT::BehaviorTreeFactory factory;
  registerPenNodes(factory);
  auto blackboard = BT::Blackboard::create();
  blackboard->set("job_id", "job");
  blackboard->set("cell_id", "cell");
  blackboard->set("recipe_id", "recipe");
  blackboard->set("recipe_version", std::uint32_t{1});
  blackboard->set("input_payload_json", "[]");
  blackboard->set("execution_mode", "simulation");
  const std::string xml = R"(
    <root BTCPP_format="4"><BehaviorTree ID="Main">
      <ValidateFrozenJob job_id="{job_id}" cell_id="{cell_id}" recipe_id="{recipe_id}"
        recipe_version="{recipe_version}" input_payload_json="{input_payload_json}"
        execution_mode="{execution_mode}"/>
    </BehaviorTree></root>)";
  auto tree = factory.createTreeFromText(xml, blackboard);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::FAILURE);
  EXPECT_EQ(blackboard->get<std::string>("last_result_code"), "pen.job.invalid_frozen_input");
}

}  // namespace
}  // namespace cellforge_pen_bt_nodes
