#pragma once

#include <stop_token>

#include "cellforge_motion/motion_types.hpp"

namespace cellforge_motion {

class MotionPlanner {
 public:
  virtual ~MotionPlanner() = default;
  virtual PlannerResult moveToPose(const MotionRequest& request, std::stop_token stop_token) = 0;
  virtual PlannerResult executeManipulation(const ManipulationRequest& request,
                                            std::stop_token stop_token) = 0;
  virtual SceneSyncResult syncPlanningScene(const SceneSyncRequest& request) = 0;
  virtual void cancelActiveRequest() = 0;
};

}  // namespace cellforge_motion
