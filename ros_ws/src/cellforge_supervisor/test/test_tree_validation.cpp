#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "cellforge_supervisor/supervisor_nodes.hpp"
#include "cellforge_supervisor/tree_validation.hpp"

namespace cellforge_supervisor {
namespace {

void configureFactory(BT::BehaviorTreeFactory& factory) { registerSupervisorNodes(factory); }

TEST(TreeValidation, ValidatesAndTicksKnownCondition) {
  BT::BehaviorTreeFactory factory;
  configureFactory(factory);
  auto blackboard = BT::Blackboard::create();
  blackboard->set("cell_ready", true);
  const std::string xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="Main">
        <CellReady cell_ready="{cell_ready}"/>
      </BehaviorTree>
    </root>)";

  auto tree = createValidatedTreeFromText(factory, xml, blackboard);
  EXPECT_EQ(tree.tickOnce(), BT::NodeStatus::SUCCESS);
}

TEST(TreeValidation, RejectsUnknownNodeBeforeTick) {
  BT::BehaviorTreeFactory factory;
  configureFactory(factory);
  const std::string xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="Main"><UnknownCapability/></BehaviorTree>
    </root>)";

  try {
    (void)createValidatedTreeFromText(factory, xml, BT::Blackboard::create());
    FAIL() << "Expected invalid XML to be rejected";
  } catch (const TreeValidationError& error) {
    EXPECT_EQ(error.code(), "supervisor.tree.invalid_xml");
  }
}

TEST(TreeValidation, RejectsMissingRequiredPortBeforeTick) {
  BT::BehaviorTreeFactory factory;
  configureFactory(factory);
  const std::string xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="Main"><CellReady/></BehaviorTree>
    </root>)";

  try {
    (void)createValidatedTreeFromText(factory, xml, BT::Blackboard::create());
    FAIL() << "Expected missing port to be rejected";
  } catch (const TreeValidationError& error) {
    EXPECT_EQ(error.code(), "supervisor.tree.missing_port");
  }
}

TEST(TreeValidation, RejectsMissingBlackboardInputBeforeTick) {
  BT::BehaviorTreeFactory factory;
  configureFactory(factory);
  const std::string xml = R"(
    <root BTCPP_format="4">
      <BehaviorTree ID="Main"><CellReady cell_ready="{not_seeded}"/></BehaviorTree>
    </root>)";

  try {
    (void)createValidatedTreeFromText(factory, xml, BT::Blackboard::create());
    FAIL() << "Expected missing blackboard input to be rejected";
  } catch (const TreeValidationError& error) {
    EXPECT_EQ(error.code(), "supervisor.tree.missing_blackboard_input");
  }
}

TEST(TreeValidation, ResolvesOnlyExactVersionedIdentifiers) {
  const std::filesystem::path root("/bundle/trees");
  EXPECT_EQ(resolveTreePath(root, "pick-part@2.1.0"), root / "pick-part@2.1.0.xml");
  EXPECT_THROW(resolveTreePath(root, "../outside"), TreeValidationError);
  EXPECT_THROW(resolveTreePath(root, "nested/tree"), TreeValidationError);
  EXPECT_THROW(resolveTreePath(root, ""), TreeValidationError);
}

}  // namespace
}  // namespace cellforge_supervisor
