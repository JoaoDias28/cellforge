#include "cellforge_motion/mtc_task_builder.hpp"

#include <moveit/task_constructor/solvers/pipeline_planner.h>
#include <moveit/task_constructor/stages/current_state.h>
#include <moveit/task_constructor/stages/fixed_state.h>
#include <moveit/task_constructor/stages/modify_planning_scene.h>
#include <moveit/task_constructor/stages/move_to.h>
#include <moveit/task_constructor/task.h>

#include <memory>
#include <moveit/planning_scene/planning_scene.hpp>
#include <stdexcept>
#include <string>
#include <utility>

namespace cellforge_motion {
namespace mtc = moveit::task_constructor;

namespace {
void addScene(mtc::Task& task, const moveit_msgs::msg::PlanningScene& scene_message) {
  auto scene = std::make_shared<planning_scene::PlanningScene>(task.getRobotModel());
  if (!scene->usePlanningSceneMsg(scene_message)) {
    throw std::invalid_argument("MTC could not load the synchronized MoveIt planning scene");
  }
  task.add(std::make_unique<mtc::stages::FixedState>("validate_synchronized_scene", scene));
}
}  // namespace

MtcTaskBuilder::MtcTaskBuilder(rclcpp::Node::SharedPtr node, std::string planning_group)
    : node_(std::move(node)), planning_group_(std::move(planning_group)) {
  if (!node_ || planning_group_.empty()) {
    throw std::invalid_argument("MTC builder requires a node and planning group");
  }
}

auto MtcTaskBuilder::build(const ManipulationRequest& request,
                           const moveit_msgs::msg::PlanningScene& planning_scene,
                           bool include_live_stages) const -> std::unique_ptr<mtc::Task> {
  auto task = std::make_unique<mtc::Task>();
  task->stages()->setName("cellforge_" + request.object_id);
  task->loadRobotModel(node_);
  task->setProperty("group", planning_group_);
  task->setProperty("ik_frame", request.tool_frame);

  addScene(*task, planning_scene);
  if (!include_live_stages) {
    return task;
  }
  auto planner = std::make_shared<mtc::solvers::PipelinePlanner>(node_);
  task->add(std::make_unique<mtc::stages::CurrentState>("current_state"));

  auto approach = std::make_unique<mtc::stages::MoveTo>("approach_safe_pose", planner);
  approach->setGroup(planning_group_);
  approach->setGoal(request.named_safe_pose);
  task->add(std::move(approach));

  auto move_to_object = std::make_unique<mtc::stages::MoveTo>("move_to_object_pose", planner);
  move_to_object->setGroup(planning_group_);
  move_to_object->setIKFrame(request.tool_frame);
  move_to_object->setGoal(request.object_pose);
  task->add(std::move(move_to_object));

  auto attachment = std::make_unique<mtc::stages::ModifyPlanningScene>("update_object_attachment");
  if (request.operation == ManipulationOperation::PICK ||
      request.operation == ManipulationOperation::UNLOAD) {
    attachment->attachObject(request.object_id, request.tool_frame);
  } else if (request.operation == ManipulationOperation::LOAD) {
    attachment->detachObject(request.object_id, request.tool_frame);
  }
  task->add(std::move(attachment));

  auto retreat = std::make_unique<mtc::stages::MoveTo>("retreat_to_safe_pose", planner);
  retreat->setGroup(planning_group_);
  retreat->setGoal(request.named_safe_pose);
  task->add(std::move(retreat));
  return task;
}

auto MtcTaskBuilder::buildMove(const MotionRequest& request,
                               const moveit_msgs::msg::PlanningScene& scene,
                               bool include_live_stages) const -> std::unique_ptr<mtc::Task> {
  auto task = std::make_unique<mtc::Task>();
  task->stages()->setName("cellforge_move_to_pose_" + request.named_pose);
  task->loadRobotModel(node_);
  task->setProperty("group", planning_group_);
  addScene(*task, scene);
  if (!include_live_stages) {
    return task;
  }
  auto planner = std::make_shared<mtc::solvers::PipelinePlanner>(node_);
  task->add(std::make_unique<mtc::stages::CurrentState>("current_state"));
  auto move = std::make_unique<mtc::stages::MoveTo>("move_to_pose", planner);
  move->setGroup(planning_group_);
  if (!request.named_pose.empty()) {
    move->setGoal(request.named_pose);
  } else {
    move->setGoal(request.target_pose);
  }
  task->add(std::move(move));
  return task;
}

}  // namespace cellforge_motion
