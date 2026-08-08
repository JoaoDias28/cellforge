#pragma once

#include <behaviortree_cpp/bt_factory.h>

#include <filesystem>
#include <stdexcept>
#include <string>

namespace cellforge_supervisor {

class TreeValidationError : public std::runtime_error {
 public:
  TreeValidationError(std::string code, std::string message);

  [[nodiscard]] const std::string& code() const noexcept;

 private:
  std::string code_;
};

std::filesystem::path resolveTreePath(const std::filesystem::path& tree_root,
                                      const std::string& task_id);

BT::Tree createValidatedTreeFromText(BT::BehaviorTreeFactory& factory, const std::string& xml,
                                     const BT::Blackboard::Ptr& blackboard);

BT::Tree createValidatedTreeFromFile(BT::BehaviorTreeFactory& factory,
                                     const std::filesystem::path& path,
                                     const BT::Blackboard::Ptr& blackboard);

void validateTreePorts(const BT::Tree& tree);

}  // namespace cellforge_supervisor
