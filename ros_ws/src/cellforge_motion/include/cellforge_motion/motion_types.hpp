#pragma once

#include <chrono>
#include <functional>
#include <geometry_msgs/msg/pose_stamped.hpp>
#include <moveit_msgs/msg/planning_scene.hpp>
#include <moveit_msgs/msg/robot_trajectory.hpp>
#include <string>
#include <vector>

namespace cellforge_motion {

enum class PlannerOutcome {
  SUCCESS,
  INVALID_INPUT,
  UNREACHABLE,
  COLLISION,
  SCENE_REJECTED,
  PLANNING_FAILED,
  EXECUTION_FAILED,
  OUTCOME_UNKNOWN,
};

enum class ManipulationOperation { PICK, LOAD, UNLOAD };

struct MotionRequest {
  std::string component_instance_id;
  std::string command_id;
  std::string trace_id;
  geometry_msgs::msg::PoseStamped target_pose;
  std::string named_pose;
  bool plan_only{true};
  double max_velocity_scaling{1.0};
  double max_acceleration_scaling{1.0};
  std::chrono::milliseconds timeout{5000};
};

struct ManipulationRequest {
  std::string component_instance_id;
  std::string command_id;
  std::string trace_id;
  ManipulationOperation operation{ManipulationOperation::PICK};
  std::string object_id;
  geometry_msgs::msg::PoseStamped object_pose;
  std::string tool_frame;
  std::string named_safe_pose;
  bool plan_only{true};
  double max_velocity_scaling{1.0};
  double max_acceleration_scaling{1.0};
  std::chrono::milliseconds timeout{10000};
};

struct SceneSyncRequest {
  std::string cell_id;
  std::string scene_revision;
  std::string cell_yaml_sha256;
  std::string usd_sha256;
  std::vector<std::string> component_instance_ids;
  moveit_msgs::msg::PlanningScene planning_scene;
};

struct PlannerResult {
  PlannerOutcome outcome{PlannerOutcome::PLANNING_FAILED};
  std::string message;
  moveit_msgs::msg::RobotTrajectory trajectory;
  double planning_time_seconds{0.0};
  std::vector<std::string> completed_stages;
  std::string failed_stage;
  bool outcome_certain{true};
};

struct MotionResult {
  bool success{false};
  std::string result_code;
  std::string result_message;
  std::string command_id;
  std::string trace_id;
  std::string scene_revision;
  double planning_time_seconds{0.0};
  moveit_msgs::msg::RobotTrajectory trajectory;
  std::vector<std::string> completed_stages;
  std::string failed_stage;
  std::string evidence_json;
  bool outcome_certain{true};
};

struct SceneSyncResult {
  bool success{false};
  std::string result_code;
  std::string result_message;
  std::string applied_scene_revision;
  std::string evidence_json;
};

using CancellationRequested = std::function<bool()>;

}  // namespace cellforge_motion
