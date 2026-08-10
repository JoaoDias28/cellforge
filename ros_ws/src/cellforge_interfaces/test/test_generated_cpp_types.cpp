#include <gtest/gtest.h>

#include <action_msgs/srv/cancel_goal.hpp>
#include <string>

#include "cellforge_interfaces/action/execute_manipulation.hpp"
#include "cellforge_interfaces/action/execute_process.hpp"
#include "cellforge_interfaces/action/execute_skill.hpp"
#include "cellforge_interfaces/action/inspect_object.hpp"
#include "cellforge_interfaces/action/locate_object.hpp"
#include "cellforge_interfaces/action/move_to_pose.hpp"
#include "cellforge_interfaces/action/run_job.hpp"
#include "cellforge_interfaces/msg/cell_state.hpp"
#include "cellforge_interfaces/msg/device_state.hpp"
#include "cellforge_interfaces/msg/job_event.hpp"
#include "cellforge_interfaces/msg/pose_estimate.hpp"
#include "cellforge_interfaces/msg/safety_state.hpp"
#include "cellforge_interfaces/srv/configure_simulation.hpp"
#include "cellforge_interfaces/srv/control_simulation.hpp"
#include "cellforge_interfaces/srv/finalize_simulation.hpp"
#include "cellforge_interfaces/srv/get_device_state.hpp"
#include "cellforge_interfaces/srv/inject_simulation_fault.hpp"
#include "cellforge_interfaces/srv/register_simulation_adapter.hpp"
#include "cellforge_interfaces/srv/set_discrete_output.hpp"
#include "cellforge_interfaces/srv/sync_planning_scene.hpp"
#include "cellforge_interfaces/srv/validate_recipe.hpp"

TEST(GeneratedCppTypes, ConstructsEveryGeneratedInterfaceType) {
  cellforge_interfaces::msg::CellState cell_state;
  cellforge_interfaces::msg::DeviceState device_state;
  cellforge_interfaces::msg::JobEvent job_event;
  cellforge_interfaces::msg::PoseEstimate pose_estimate;
  cellforge_interfaces::msg::SafetyState safety_state;
  cellforge_interfaces::srv::GetDeviceState::Request state_request;
  cellforge_interfaces::srv::ConfigureSimulation::Request configure_simulation;
  cellforge_interfaces::srv::ControlSimulation::Request control_simulation;
  cellforge_interfaces::srv::FinalizeSimulation::Request finalize_simulation;
  cellforge_interfaces::srv::InjectSimulationFault::Request inject_fault;
  cellforge_interfaces::srv::RegisterSimulationAdapter::Request register_adapter;
  cellforge_interfaces::srv::SetDiscreteOutput::Request output_request;
  cellforge_interfaces::srv::SyncPlanningScene::Request scene_request;
  cellforge_interfaces::srv::ValidateRecipe::Request recipe_request;
  cellforge_interfaces::action::ExecuteProcess::Goal process_goal;
  cellforge_interfaces::action::ExecuteManipulation::Goal manipulation_goal;
  cellforge_interfaces::action::ExecuteSkill::Goal skill_goal;
  cellforge_interfaces::action::InspectObject::Goal inspection_goal;
  cellforge_interfaces::action::LocateObject::Goal locate_goal;
  cellforge_interfaces::action::MoveToPose::Goal move_goal;
  cellforge_interfaces::action::RunJob::Goal job_goal;

  EXPECT_TRUE(cell_state.devices.empty());
  EXPECT_FALSE(device_state.ready);
  EXPECT_EQ(job_event.sequence, 0U);
  EXPECT_FLOAT_EQ(pose_estimate.confidence, 0.0F);
  EXPECT_FALSE(safety_state.healthy);
  EXPECT_TRUE(state_request.component_instance_id.empty());
  EXPECT_TRUE(configure_simulation.project_path.empty());
  EXPECT_TRUE(control_simulation.command.empty());
  EXPECT_TRUE(finalize_simulation.evidence_path.empty());
  EXPECT_TRUE(inject_fault.fault_code.empty());
  EXPECT_TRUE(register_adapter.component_instance_id.empty());
  EXPECT_FALSE(output_request.value);
  EXPECT_TRUE(scene_request.scene_revision.empty());
  EXPECT_TRUE(recipe_request.recipe_json.empty());
  EXPECT_EQ(process_goal.timeout.sec, 0);
  EXPECT_EQ(manipulation_goal.timeout.sec, 0);
  EXPECT_EQ(skill_goal.timeout.sec, 0);
  EXPECT_EQ(inspection_goal.timeout.sec, 0);
  EXPECT_EQ(locate_goal.timeout.sec, 0);
  EXPECT_EQ(move_goal.timeout.sec, 0);
  EXPECT_EQ(job_goal.timeout.sec, 0);
}

TEST(GeneratedCppTypes, RepresentsSuccessfulResult) {
  cellforge_interfaces::action::ExecuteSkill::Result result;
  result.success = true;
  result.result_code = "skill.success";
  result.output_payload_json = "{}";

  EXPECT_TRUE(result.success);
  EXPECT_EQ(result.result_code, "skill.success");
}

TEST(GeneratedCppTypes, RepresentsInvalidInputFailure) {
  cellforge_interfaces::srv::ValidateRecipe::Response result;
  result.valid = false;
  result.validation_report_json = R"({"code":"recipe.invalid"})";

  EXPECT_FALSE(result.valid);
  EXPECT_NE(result.validation_report_json.find("recipe.invalid"), std::string::npos);
}

TEST(GeneratedCppTypes, RepresentsCallerTimeout) {
  cellforge_interfaces::action::RunJob::Goal goal;
  goal.timeout.sec = 30;

  EXPECT_EQ(goal.timeout.sec, 30);
}

TEST(GeneratedCppTypes, UsesStandardActionCancellationProtocol) {
  action_msgs::srv::CancelGoal::Request request;

  EXPECT_EQ(request.goal_info.goal_id.uuid.size(), 16U);
}

TEST(GeneratedCppTypes, RepresentsDeterministicFailureAndUncertainOutcome) {
  cellforge_interfaces::action::ExecuteProcess::Result result;
  result.success = false;
  result.result_code = "process.communication.timeout";
  result.outcome_certain = false;

  EXPECT_FALSE(result.success);
  EXPECT_EQ(result.result_code, "process.communication.timeout");
  EXPECT_FALSE(result.outcome_certain);
}
