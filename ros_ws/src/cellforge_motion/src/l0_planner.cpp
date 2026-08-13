#include "cellforge_motion/l0_planner.hpp"

#include <chrono>
#include <thread>
#include <utility>

using namespace std::chrono_literals;

namespace cellforge_motion {
namespace {
constexpr int kContractTicks = 5;
constexpr double kContractPlanningSeconds = 0.025;
constexpr auto kContractTickDuration = 5ms;
}  // namespace

auto L0Planner::moveToPose(const MotionRequest& /*request*/, std::stop_token stop_token)
    -> PlannerResult {
  return complete(stop_token, {"contract_plan", "contract_execute"});
}

auto L0Planner::executeManipulation(const ManipulationRequest& request, std::stop_token stop_token)
    -> PlannerResult {
  std::vector<std::string> stages{"current_state", "approach", "operate", "retreat"};
  if (request.operation == ManipulationOperation::LOAD) {
    stages[2] = "load";
  } else if (request.operation == ManipulationOperation::UNLOAD) {
    stages[2] = "unload";
  } else {
    stages[2] = "pick";
  }
  return complete(stop_token, std::move(stages));
}

auto L0Planner::syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult {
  cancelled_.store(false);
  return {true,
          "motion.scene.synchronized",
          "L0 contract scene identity accepted.",
          request.scene_revision,
          {}};
}

void L0Planner::cancelActiveRequest() { cancelled_.store(true); }

auto L0Planner::complete(const std::stop_token& stop_token, std::vector<std::string> stages)
    -> PlannerResult {
  cancelled_.store(false);
  for (int tick = 0; tick < kContractTicks; ++tick) {
    if (stop_token.stop_requested() || cancelled_.load()) {
      return {PlannerOutcome::EXECUTION_FAILED,
              "L0 motion cancelled.",
              moveit_msgs::msg::RobotTrajectory(),
              0.0,
              {},
              "cancelled"};
    }
    std::this_thread::sleep_for(kContractTickDuration);
  }
  return {PlannerOutcome::SUCCESS, "L0 contract motion completed.",
          moveit_msgs::msg::RobotTrajectory(), kContractPlanningSeconds, std::move(stages)};
}

}  // namespace cellforge_motion
