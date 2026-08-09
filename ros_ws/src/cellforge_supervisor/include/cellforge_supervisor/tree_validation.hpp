#pragma once

#include <behaviortree_cpp/bt_factory.h>

#include <filesystem>
#include <stdexcept>
#include <string>

namespace cellforge_supervisor {

class TreeValidationError : public std::runtime_error {
 public:
  TreeValidationError(const char* code, const std::string& message);

  [[nodiscard]] auto code() const noexcept -> const std::string&;

 private:
  std::string code_;
};

auto resolveTreePath(const std::filesystem::path& tree_root,
                     const std::string& task_id) -> std::filesystem::path;

auto createValidatedTreeFromText(BT::BehaviorTreeFactory& factory, const std::string& xml,
                                 const BT::Blackboard::Ptr& blackboard) -> BT::Tree;

auto createValidatedTreeFromFile(BT::BehaviorTreeFactory& factory,
                                 const std::filesystem::path& path,
                                 const BT::Blackboard::Ptr& blackboard) -> BT::Tree;

void validateTreePorts(const BT::Tree& tree);

}  // namespace cellforge_supervisor
