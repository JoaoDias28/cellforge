#include "cellforge_motion/mtc_task_builder.hpp"

#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit/task_constructor/stages/fixed_state.h>
#include <moveit/task_constructor/task.h>

#include <memory>
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
                           const moveit_msgs::msg::PlanningScene& planning_scene) const
    -> std::unique_ptr<mtc::Task> {
  auto task = std::make_unique<mtc::Task>();
  task->stages()->setName("cellforge_" + request.object_id);
  task->loadRobotModel(node_);
  task->setProperty("group", planning_group_);
  task->setProperty("ik_frame", request.tool_frame);

  addScene(*task, planning_scene);
  return task;
}

auto MtcTaskBuilder::buildMove(const MotionRequest& request,
                               const moveit_msgs::msg::PlanningScene& scene) const
    -> std::unique_ptr<mtc::Task> {
  auto task = std::make_unique<mtc::Task>();
  task->stages()->setName("cellforge_move_to_pose_" + request.named_pose);
  task->loadRobotModel(node_);
  task->setProperty("group", planning_group_);
  addScene(*task, scene);
  return task;
}

}  // namespace cellforge_motion
