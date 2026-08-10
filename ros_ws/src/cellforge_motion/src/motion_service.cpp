#include "cellforge_motion/motion_service.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <future>
#include <iomanip>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <unordered_set>
#include <utility>

namespace cellforge_motion {
namespace {
using namespace std::chrono_literals;

constexpr std::array<const char*, 4> kSafePoses{"home", "process_safe", "load_safe", "unload_safe"};
const std::regex kUuidPattern(
    "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$");
const std::regex kSha256Pattern("^[0-9a-f]{64}$");
const std::regex kStableIdPattern("^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$");

bool safePose(const std::string& value) {
  return std::find(kSafePoses.begin(), kSafePoses.end(), value) != kSafePoses.end();
}

bool validPose(const geometry_msgs::msg::PoseStamped& pose) {
  const auto& p = pose.pose.position;
  const auto& q = pose.pose.orientation;
  const auto norm = q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w;
  return !pose.header.frame_id.empty() && std::isfinite(p.x) && std::isfinite(p.y) &&
         std::isfinite(p.z) && std::isfinite(norm) && std::abs(norm - 1.0) <= 1e-3;
}

bool validScaling(double value) { return std::isfinite(value) && value > 0.0 && value <= 1.0; }

std::string escapeJson(const std::string& value) {
  std::string escaped;
  escaped.reserve(value.size());
  for (const char character : value) {
    if (character == '\\' || character == '"') {
      escaped.push_back('\\');
    }
    escaped.push_back(character);
  }
  return escaped;
}

std::pair<std::string, std::string> mappedCode(PlannerOutcome outcome, bool plan_only) {
  switch (outcome) {
    case PlannerOutcome::SUCCESS:
      return {plan_only ? "motion.plan.completed" : "motion.execution.completed", "completed"};
    case PlannerOutcome::INVALID_INPUT:
      return {"motion.request.invalid_input", "invalid input"};
    case PlannerOutcome::UNREACHABLE:
      return {"motion.plan.unreachable", "target is unreachable"};
    case PlannerOutcome::COLLISION:
      return {"motion.plan.collision", "collision-free plan not found"};
    case PlannerOutcome::SCENE_REJECTED:
      return {"motion.scene.rejected", "planning scene rejected"};
    case PlannerOutcome::EXECUTION_FAILED:
      return {"motion.execution.failed", "trajectory execution failed"};
    case PlannerOutcome::OUTCOME_UNKNOWN:
      return {"motion.execution.outcome_unknown", "execution outcome is unknown"};
    case PlannerOutcome::PLANNING_FAILED:
      return {"motion.plan.failed", "planning failed"};
  }
  return {"motion.plan.failed", "planning failed"};
}
}  // namespace

MotionService::MotionService(std::shared_ptr<MotionPlanner> planner)
    : planner_(std::move(planner)) {
  if (!planner_) {
    throw std::invalid_argument("planner must not be null");
  }
}

MotionResult MotionService::moveToPose(const MotionRequest& request,
                                       const CancellationRequested& cancellation_requested) {
  if (const auto error = validate(request); !error.empty()) {
    PlannerResult invalid{PlannerOutcome::INVALID_INPUT, error};
    return mapResult(request.command_id, request.trace_id, request.plan_only, invalid);
  }
  if (sceneRevision().empty()) {
    PlannerResult missing{PlannerOutcome::SCENE_REJECTED,
                          "Planning scene must be synchronized before planning."};
    return mapResult(request.command_id, request.trace_id, request.plan_only, missing);
  }
  return run(request.command_id, request.trace_id, request.plan_only, request.timeout,
             cancellation_requested, [this, &request](std::stop_token token) {
               return planner_->moveToPose(request, token);
             });
}

MotionResult MotionService::executeManipulation(
    const ManipulationRequest& request, const CancellationRequested& cancellation_requested) {
  if (const auto error = validate(request); !error.empty()) {
    PlannerResult invalid{PlannerOutcome::INVALID_INPUT, error};
    return mapResult(request.command_id, request.trace_id, request.plan_only, invalid);
  }
  if (sceneRevision().empty()) {
    PlannerResult missing{PlannerOutcome::SCENE_REJECTED,
                          "Planning scene must be synchronized before planning."};
    return mapResult(request.command_id, request.trace_id, request.plan_only, missing);
  }
  return run(request.command_id, request.trace_id, request.plan_only, request.timeout,
             cancellation_requested, [this, &request](std::stop_token token) {
               return planner_->executeManipulation(request, token);
             });
}

SceneSyncResult MotionService::syncPlanningScene(const SceneSyncRequest& request) {
  if (const auto error = validate(request); !error.empty()) {
    return {false,
            "motion.scene.invalid_input",
            error,
            {},
            sceneEvidence(request, false, "motion.scene.invalid_input")};
  }
  auto result = planner_->syncPlanningScene(request);
  if (result.success) {
    std::scoped_lock lock(mutex_);
    scene_revision_ = request.scene_revision;
    result.applied_scene_revision = request.scene_revision;
    result.result_code = "motion.scene.synchronized";
  } else if (result.result_code.empty()) {
    result.result_code = "motion.scene.apply_failed";
  }
  result.evidence_json = sceneEvidence(request, result.success, result.result_code);
  return result;
}

std::string MotionService::sceneRevision() const {
  std::scoped_lock lock(mutex_);
  return scene_revision_;
}

MotionResult MotionService::run(const std::string& command_id, const std::string& trace_id,
                                bool plan_only, std::chrono::milliseconds timeout,
                                const CancellationRequested& cancellation_requested,
                                const std::function<PlannerResult(std::stop_token)>& callable) {
  std::promise<PlannerResult> promise;
  auto future = promise.get_future();
  std::jthread worker([&promise, &callable](std::stop_token token) {
    try {
      promise.set_value(callable(token));
    } catch (const std::exception& error) {
      promise.set_value(PlannerResult{PlannerOutcome::OUTCOME_UNKNOWN,
                                      std::string("Planner exception: ") + error.what(),
                                      moveit_msgs::msg::RobotTrajectory(),
                                      0.0,
                                      {},
                                      {},
                                      false});
    } catch (...) {
      promise.set_value(PlannerResult{PlannerOutcome::OUTCOME_UNKNOWN,
                                      "Unknown planner exception.",
                                      moveit_msgs::msg::RobotTrajectory(),
                                      0.0,
                                      {},
                                      {},
                                      false});
    }
  });

  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (future.wait_for(5ms) != std::future_status::ready) {
    if (cancellation_requested()) {
      worker.request_stop();
      planner_->cancelActiveRequest();
      worker.join();
      PlannerResult cancelled{PlannerOutcome::EXECUTION_FAILED,
                              "Cancellation requested; active planning/execution was stopped."};
      auto result = mapResult(command_id, trace_id, plan_only, cancelled);
      result.result_code = "motion.request.cancelled";
      return result;
    }
    if (std::chrono::steady_clock::now() >= deadline) {
      worker.request_stop();
      planner_->cancelActiveRequest();
      worker.join();
      PlannerResult timed_out{PlannerOutcome::EXECUTION_FAILED,
                              "Motion deadline elapsed; cancellation was requested."};
      auto result = mapResult(command_id, trace_id, plan_only, timed_out);
      result.result_code = "motion.request.timeout";
      return result;
    }
  }
  auto result = mapResult(command_id, trace_id, plan_only, future.get());
  worker.join();
  return result;
}

MotionResult MotionService::mapResult(const std::string& command_id, const std::string& trace_id,
                                      bool plan_only, const PlannerResult& planner_result) const {
  const auto [code, fallback] = mappedCode(planner_result.outcome, plan_only);
  MotionResult result;
  result.success = planner_result.outcome == PlannerOutcome::SUCCESS;
  result.result_code = code;
  result.result_message = planner_result.message.empty() ? fallback : planner_result.message;
  result.command_id = command_id;
  result.trace_id = trace_id;
  result.scene_revision = sceneRevision();
  result.planning_time_seconds = planner_result.planning_time_seconds;
  result.trajectory = planner_result.trajectory;
  result.completed_stages = planner_result.completed_stages;
  result.failed_stage = planner_result.failed_stage;
  result.outcome_certain = planner_result.outcome_certain;
  result.evidence_json = evidence(result, plan_only);
  return result;
}

std::string MotionService::validate(const MotionRequest& request) {
  if (!std::regex_match(request.component_instance_id, kStableIdPattern)) {
    return "component_instance_id is invalid";
  }
  if (!std::regex_match(request.command_id, kUuidPattern) ||
      !std::regex_match(request.trace_id, kUuidPattern)) {
    return "command_id and trace_id must be UUIDs";
  }
  const bool has_named = !request.named_pose.empty();
  const bool has_pose = !request.target_pose.header.frame_id.empty();
  if (has_named == has_pose) {
    return "exactly one named_pose or target_pose is required";
  }
  if ((has_named && !safePose(request.named_pose)) ||
      (has_pose && !validPose(request.target_pose))) {
    return "target pose is invalid or not a declared safe pose";
  }
  if (!validScaling(request.max_velocity_scaling) ||
      !validScaling(request.max_acceleration_scaling) || request.timeout <= 0ms) {
    return "scaling must be in (0, 1] and timeout must be positive";
  }
  return {};
}

std::string MotionService::validate(const ManipulationRequest& request) {
  if (!std::regex_match(request.component_instance_id, kStableIdPattern) ||
      !std::regex_match(request.command_id, kUuidPattern) ||
      !std::regex_match(request.trace_id, kUuidPattern)) {
    return "component instance and command/trace identities are invalid";
  }
  if (!std::regex_match(request.object_id, kStableIdPattern) ||
      !std::regex_match(request.tool_frame, kStableIdPattern)) {
    return "object_id and tool_frame must be stable identifiers";
  }
  if (!validPose(request.object_pose) || !safePose(request.named_safe_pose)) {
    return "object_pose and a declared named safe pose are required";
  }
  if (!validScaling(request.max_velocity_scaling) ||
      !validScaling(request.max_acceleration_scaling) || request.timeout <= 0ms) {
    return "scaling must be in (0, 1] and timeout must be positive";
  }
  return {};
}

std::string MotionService::validate(const SceneSyncRequest& request) {
  if (!std::regex_match(request.cell_id, kUuidPattern) ||
      !std::regex_match(request.scene_revision, kStableIdPattern) ||
      !std::regex_match(request.cell_yaml_sha256, kSha256Pattern) ||
      !std::regex_match(request.usd_sha256, kSha256Pattern) ||
      request.component_instance_ids.empty()) {
    return "cell, revision, SHA-256 identities, and component IDs are required";
  }
  std::unordered_set<std::string> ids;
  for (const auto& id : request.component_instance_ids) {
    if (!std::regex_match(id, kStableIdPattern) || !ids.insert(id).second) {
      return "component instance IDs must be unique stable identifiers";
    }
  }
  for (const auto& object : request.planning_scene.world.collision_objects) {
    const auto separator = object.id.find('/');
    const auto owner = object.id.substr(0, separator);
    if (!ids.contains(owner)) {
      return "collision object IDs must be owned by a declared component instance";
    }
  }
  return {};
}

std::string MotionService::evidence(const MotionResult& result, bool plan_only) {
  std::ostringstream stream;
  stream << std::setprecision(17);
  stream << "{\"command_id\":\"" << escapeJson(result.command_id) << "\",\"trace_id\":\""
         << escapeJson(result.trace_id) << "\",\"scene_revision\":\""
         << escapeJson(result.scene_revision) << "\",\"mode\":\""
         << (plan_only ? "plan_only" : "plan_and_execute") << "\",\"result_code\":\""
         << escapeJson(result.result_code)
         << "\",\"planning_time_seconds\":" << result.planning_time_seconds
         << ",\"completed_stages\":[";
  for (std::size_t index = 0; index < result.completed_stages.size(); ++index) {
    if (index > 0) {
      stream << ',';
    }
    stream << '"' << escapeJson(result.completed_stages[index]) << '"';
  }
  stream << "],\"failed_stage\":\"" << escapeJson(result.failed_stage)
         << "\",\"outcome_certain\":" << (result.outcome_certain ? "true" : "false")
         << ",\"safety_claim\":\"none; standard-control motion evidence only\"}";
  return stream.str();
}

std::string MotionService::sceneEvidence(const SceneSyncRequest& request, bool success,
                                         const std::string& code) {
  std::ostringstream stream;
  stream << "{\"cell_id\":\"" << escapeJson(request.cell_id) << "\",\"scene_revision\":\""
         << escapeJson(request.scene_revision) << "\",\"cell_yaml_sha256\":\""
         << request.cell_yaml_sha256 << "\",\"usd_sha256\":\"" << request.usd_sha256
         << "\",\"result_code\":\"" << escapeJson(code)
         << "\",\"success\":" << (success ? "true" : "false") << "}";
  return stream.str();
}

}  // namespace cellforge_motion
