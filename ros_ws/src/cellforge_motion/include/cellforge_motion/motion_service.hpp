#pragma once

#include <memory>
#include <mutex>
#include <string>

#include "cellforge_motion/motion_planner.hpp"

namespace cellforge_motion {

class MotionService {
 public:
  explicit MotionService(std::shared_ptr<MotionPlanner> planner);

  MotionResult moveToPose(
      const MotionRequest& request,
      const CancellationRequested& cancellation_requested = [] { return false; });
  MotionResult executeManipulation(
      const ManipulationRequest& request,
      const CancellationRequested& cancellation_requested = [] { return false; });
  SceneSyncResult syncPlanningScene(const SceneSyncRequest& request);

  [[nodiscard]] std::string sceneRevision() const;

 private:
  MotionResult run(const std::string& command_id, const std::string& trace_id, bool plan_only,
                   std::chrono::milliseconds timeout,
                   const CancellationRequested& cancellation_requested,
                   const std::function<PlannerResult(std::stop_token)>& callable);
  MotionResult mapResult(const std::string& command_id, const std::string& trace_id, bool plan_only,
                         const PlannerResult& planner_result) const;
  static std::string validate(const MotionRequest& request);
  static std::string validate(const ManipulationRequest& request);
  static std::string validate(const SceneSyncRequest& request);
  static std::string evidence(const MotionResult& result, bool plan_only);
  static std::string sceneEvidence(const SceneSyncRequest& request, bool success,
                                   const std::string& code);

  std::shared_ptr<MotionPlanner> planner_;
  mutable std::mutex mutex_;
  std::string scene_revision_;
};

}  // namespace cellforge_motion
