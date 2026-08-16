#pragma once

#include <atomic>

#include "cellforge_motion/motion_planner.hpp"

namespace cellforge_motion {

class L0Planner final : public MotionPlanner {
 public:
  auto moveToPose(const MotionRequest& request, std::stop_token stop_token)
      -> PlannerResult override;
  auto executeManipulation(const ManipulationRequest& request, std::stop_token stop_token)
      -> PlannerResult override;
  auto syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult override;
  void cancelActiveRequest() override;

 private:
  auto complete(const std::stop_token& stop_token, std::vector<std::string> stages)
      -> PlannerResult;

  std::atomic_bool cancelled_{false};
};

}  // namespace cellforge_motion
