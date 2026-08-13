#pragma once

#include <memory>
#include <mutex>
#include <string>

#include "cellforge_motion/motion_planner.hpp"

namespace cellforge_motion {

class MotionService {
 public:
  explicit MotionService(std::shared_ptr<MotionPlanner> planner);

  auto moveToPose(
      const MotionRequest& request,
      const CancellationRequested& cancellation_requested = [] { return false; }) -> MotionResult;
  auto executeManipulation(
      const ManipulationRequest& request,
      const CancellationRequested& cancellation_requested = [] { return false; }) -> MotionResult;
  auto syncPlanningScene(const SceneSyncRequest& request) -> SceneSyncResult;

  [[nodiscard]] auto sceneRevision() const -> std::string;

 private:
  auto run(const std::string& command_id, const std::string& trace_id, bool plan_only,
           std::chrono::milliseconds timeout, const CancellationRequested& cancellation_requested,
           const std::function<PlannerResult(std::stop_token)>& callable) -> MotionResult;
  auto mapResult(const std::string& command_id, const std::string& trace_id, bool plan_only,
                 const PlannerResult& planner_result) const -> MotionResult;
  static auto validate(const MotionRequest& request) -> std::string;
  static auto validate(const ManipulationRequest& request) -> std::string;
  static auto validate(const SceneSyncRequest& request) -> std::string;
  static auto evidence(const MotionResult& result, bool plan_only) -> std::string;
  static auto sceneEvidence(const SceneSyncRequest& request, bool success, const std::string& code)
      -> std::string;

  std::shared_ptr<MotionPlanner> planner_;
  mutable std::mutex mutex_;
  std::string scene_revision_;
};

}  // namespace cellforge_motion
