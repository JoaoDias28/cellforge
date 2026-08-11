#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <memory>
#include <stop_token>
#include <string>
#include <thread>

#include "cellforge_motion/l0_planner.hpp"
#include "cellforge_motion/motion_service.hpp"

namespace cellforge_motion {
namespace {
using namespace std::chrono_literals;

constexpr auto kCommand = "11111111-1111-4111-8111-111111111111";
constexpr auto kTrace = "22222222-2222-4222-8222-222222222222";
constexpr auto kCell = "33333333-3333-4333-8333-333333333333";
constexpr auto kHashA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
constexpr auto kHashB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

class FakePlanner final : public MotionPlanner {
 public:
  PlannerResult next{PlannerOutcome::SUCCESS, "fake completed"};
  SceneSyncResult scene{true, "", "fake scene applied"};
  std::atomic_bool entered{false};
  std::atomic_bool cancelled{false};
  bool block{false};
  int pose_calls{0};

  PlannerResult moveToPose(const MotionRequest&, std::stop_token token) override {
    ++pose_calls;
    entered.store(true);
    while (block && !token.stop_requested()) std::this_thread::sleep_for(1ms);
    return next;
  }
  PlannerResult executeManipulation(const ManipulationRequest&, std::stop_token token) override {
    entered.store(true);
    while (block && !token.stop_requested()) std::this_thread::sleep_for(1ms);
    return next;
  }
  SceneSyncResult syncPlanningScene(const SceneSyncRequest&) override { return scene; }
  void cancelActiveRequest() override { cancelled.store(true); }
};

SceneSyncRequest sceneRequest() {
  return {kCell,
          "scene-0001",
          kHashA,
          kHashB,
          {"robot-001", "fixture-001"},
          moveit_msgs::msg::PlanningScene()};
}

MotionRequest motionRequest(bool plan_only = true) {
  MotionRequest request;
  request.component_instance_id = "robot-001";
  request.command_id = kCommand;
  request.trace_id = kTrace;
  request.named_pose = "home";
  request.plan_only = plan_only;
  request.timeout = 100ms;
  return request;
}

ManipulationRequest manipulationRequest() {
  ManipulationRequest request;
  request.component_instance_id = "robot-001";
  request.command_id = kCommand;
  request.trace_id = kTrace;
  request.operation = ManipulationOperation::PICK;
  request.object_id = "pen-001";
  request.object_pose.header.frame_id = "world";
  request.object_pose.pose.orientation.w = 1.0;
  request.tool_frame = "tool0";
  request.named_safe_pose = "load_safe";
  request.timeout = 100ms;
  return request;
}

std::shared_ptr<MotionService> serviceWith(const std::shared_ptr<FakePlanner>& planner) {
  auto service = std::make_shared<MotionService>(planner);
  EXPECT_TRUE(service->syncPlanningScene(sceneRequest()).success);
  return service;
}

TEST(MotionService, PlanOnlySucceedsWithoutControllerAndPreservesTraceEvidence) {
  auto planner = std::make_shared<FakePlanner>();
  planner->next.planning_time_seconds = 0.125;
  auto service = serviceWith(planner);
  const auto result = service->moveToPose(motionRequest());
  EXPECT_TRUE(result.success);
  EXPECT_EQ(result.result_code, "motion.plan.completed");
  EXPECT_EQ(result.command_id, kCommand);
  EXPECT_EQ(result.trace_id, kTrace);
  EXPECT_EQ(result.scene_revision, "scene-0001");
  EXPECT_NE(result.evidence_json.find("\"mode\":\"plan_only\""), std::string::npos);
  EXPECT_NE(result.evidence_json.find(kTrace), std::string::npos);
}

TEST(MotionService, PlanAndExecuteUsesFakeControllerBackend) {
  auto planner = std::make_shared<FakePlanner>();
  planner->next.completed_stages = {"plan", "execute"};
  auto service = serviceWith(planner);
  const auto result = service->moveToPose(motionRequest(false));
  EXPECT_TRUE(result.success);
  EXPECT_EQ(result.result_code, "motion.execution.completed");
  EXPECT_EQ(result.completed_stages, (std::vector<std::string>{"plan", "execute"}));
  EXPECT_NE(result.evidence_json.find("\"mode\":\"plan_and_execute\""), std::string::npos);
}

TEST(MotionService, EvidenceIsDeterministicForSameInputsAndBackendResult) {
  auto planner = std::make_shared<FakePlanner>();
  auto service = serviceWith(planner);
  const auto first = service->moveToPose(motionRequest());
  const auto second = service->moveToPose(motionRequest());
  EXPECT_EQ(first.evidence_json, second.evidence_json);
}

TEST(MotionService, InvalidInputFailsBeforePlanner) {
  auto planner = std::make_shared<FakePlanner>();
  auto service = serviceWith(planner);
  auto request = motionRequest();
  request.named_pose = "planner_specific_magic";
  const auto result = service->moveToPose(request);
  EXPECT_FALSE(result.success);
  EXPECT_EQ(result.result_code, "motion.request.invalid_input");
  EXPECT_EQ(planner->pose_calls, 0);
}

TEST(MotionService, UnreachableAndCollisionHaveStableFailures) {
  auto planner = std::make_shared<FakePlanner>();
  auto service = serviceWith(planner);
  planner->next = {PlannerOutcome::UNREACHABLE, "no inverse kinematics"};
  EXPECT_EQ(service->moveToPose(motionRequest()).result_code, "motion.plan.unreachable");
  planner->next = {PlannerOutcome::COLLISION, "goal in collision"};
  EXPECT_EQ(service->moveToPose(motionRequest()).result_code, "motion.plan.collision");
}

TEST(MotionService, TimeoutCancelsActiveBackendRequest) {
  auto planner = std::make_shared<FakePlanner>();
  planner->block = true;
  auto service = serviceWith(planner);
  auto request = motionRequest(false);
  request.timeout = 20ms;
  const auto result = service->moveToPose(request);
  EXPECT_EQ(result.result_code, "motion.request.timeout");
  EXPECT_TRUE(planner->cancelled.load());
}

TEST(MotionService, CallerCancellationStopsExecutionRequest) {
  auto planner = std::make_shared<FakePlanner>();
  planner->block = true;
  auto service = serviceWith(planner);
  std::atomic_bool cancel{false};
  std::thread requester([&] {
    while (!planner->entered.load()) std::this_thread::yield();
    cancel.store(true);
  });
  const auto result = service->moveToPose(motionRequest(false), [&] { return cancel.load(); });
  requester.join();
  EXPECT_EQ(result.result_code, "motion.request.cancelled");
  EXPECT_TRUE(planner->cancelled.load());
}

TEST(MotionService, ExecutionFailureDoesNotClaimCertainSuccess) {
  auto planner = std::make_shared<FakePlanner>();
  planner->next = {PlannerOutcome::OUTCOME_UNKNOWN,
                   "controller disconnected",
                   moveit_msgs::msg::RobotTrajectory(),
                   0.2,
                   {},
                   "execute",
                   false};
  auto service = serviceWith(planner);
  const auto result = service->moveToPose(motionRequest(false));
  EXPECT_EQ(result.result_code, "motion.execution.outcome_unknown");
  EXPECT_FALSE(result.outcome_certain);
  EXPECT_FALSE(result.success);
}

TEST(MotionService, ManipulationReturnsStableStageEvidence) {
  auto planner = std::make_shared<FakePlanner>();
  planner->next.completed_stages = {"current_state", "approach_safe_pose", "move_to_object_pose"};
  auto service = serviceWith(planner);
  const auto result = service->executeManipulation(manipulationRequest());
  EXPECT_TRUE(result.success);
  EXPECT_EQ(result.completed_stages.size(), 3U);
}

TEST(MotionService, LoadAndUnloadDoNotInventAnObjectPoseRequirement) {
  auto planner = std::make_shared<FakePlanner>();
  auto service = serviceWith(planner);
  auto request = manipulationRequest();
  request.operation = ManipulationOperation::LOAD;
  request.object_pose = geometry_msgs::msg::PoseStamped();
  EXPECT_TRUE(service->executeManipulation(request).success);
  request.operation = ManipulationOperation::UNLOAD;
  EXPECT_TRUE(service->executeManipulation(request).success);
}

TEST(L0Planner, ReportsContractFidelityAndHonorsCancellation) {
  L0Planner planner;
  const auto scene = planner.syncPlanningScene(sceneRequest());
  EXPECT_TRUE(scene.success);
  EXPECT_EQ(scene.applied_scene_revision, "scene-0001");
  std::stop_source stopped;
  stopped.request_stop();
  const auto cancelled = planner.moveToPose(motionRequest(false), stopped.get_token());
  EXPECT_EQ(cancelled.outcome, PlannerOutcome::EXECUTION_FAILED);
  const auto completed = planner.executeManipulation(manipulationRequest(), {});
  EXPECT_EQ(completed.outcome, PlannerOutcome::SUCCESS);
  EXPECT_FALSE(completed.completed_stages.empty());
}

TEST(MotionService, InvalidSceneOwnershipFailsClosed) {
  auto planner = std::make_shared<FakePlanner>();
  MotionService service(planner);
  auto request = sceneRequest();
  moveit_msgs::msg::CollisionObject object;
  object.id = "unknown-999/collision";
  request.planning_scene.world.collision_objects.push_back(object);
  const auto result = service.syncPlanningScene(request);
  EXPECT_FALSE(result.success);
  EXPECT_EQ(result.result_code, "motion.scene.invalid_input");
  EXPECT_TRUE(service.sceneRevision().empty());
}

TEST(MotionService, PlanningWithoutSynchronizedCanonicalSceneIsRejected) {
  auto planner = std::make_shared<FakePlanner>();
  MotionService service(planner);
  const auto result = service.moveToPose(motionRequest());
  EXPECT_EQ(result.result_code, "motion.scene.rejected");
  EXPECT_EQ(planner->pose_calls, 0);
}

}  // namespace
}  // namespace cellforge_motion
