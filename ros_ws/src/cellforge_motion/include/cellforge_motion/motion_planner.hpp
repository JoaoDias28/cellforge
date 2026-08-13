#pragma once

#include <stop_token>

#include "cellforge_motion/motion_types.hpp"

namespace cellforge_motion {

class MotionPlanner {
 public:
  virtual ~MotionPlanner() = default;
  virtual auto moveToPose(const MotionRequest& request, std::stop_token stop_token)
      -> PlannerResult = 0;
  virtual auto executeManipulation(const ManipulationRequest& request, std::stop_token stop_token)
      -> PlannerResult = 0;
  virtual auto syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult = 0;
  virtual void cancelActiveRequest() = 0;
};

}  // namespace cellforge_motion
