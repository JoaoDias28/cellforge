#include "cellforge_motion/mtc_task_builder.hpp"

#include <moveit/task_constructor/solvers/pipeline_planner.h>
#include <moveit/task_constructor/stages/current_state.h>
#include <moveit/task_constructor/stages/modify_planning_scene.h>
#include <moveit/task_constructor/stages/move_to.h>
#include <moveit/task_constructor/task.h>

#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

namespace cellforge_motion {
namespace mtc = moveit::task_constructor;

MtcTaskBuilder::MtcTaskBuilder(rclcpp::Node::SharedPtr node, std::string planning_group)
    : node_(std::move(node)), planning_group_(std::move(planning_group)) {
  if (!node_ || planning_group_.empty()) {
    throw std::invalid_argument("MTC builder requires a node and planning group");
  }
}

std::unique_ptr<mtc::Task> MtcTaskBuilder::build(const ManipulationRequest& request) const {
  auto task = std::make_unique<mtc::Task>();
  task->stages()->setName("cellforge_" + request.object_id);
  task->loadRobotModel(node_);
  task->setProperty("group", planning_group_);
  task->setProperty("ik_frame", request.tool_frame);

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

  auto scene = std::make_unique<mtc::stages::ModifyPlanningScene>("update_object_attachment");
  if (request.operation == ManipulationOperation::PICK ||
      request.operation == ManipulationOperation::UNLOAD) {
    scene->attachObject(request.object_id, request.tool_frame);
  } else if (request.operation == ManipulationOperation::LOAD) {
    scene->detachObject(request.object_id, request.tool_frame);
  }
  task->add(std::move(scene));

  auto retreat = std::make_unique<mtc::stages::MoveTo>("retreat_to_safe_pose", planner);
  retreat->setGroup(planning_group_);
  retreat->setGoal(request.named_safe_pose);
  task->add(std::move(retreat));
  return task;
}

}  // namespace cellforge_motion
