#include "cellforge_supervisor/tree_validation.hpp"

#include <behaviortree_cpp/tree_node.h>
#include <behaviortree_cpp/xml_parsing.h>

#include <fstream>
#include <regex>
#include <sstream>
#include <unordered_map>
#include <unordered_set>

namespace cellforge_supervisor {
namespace {

std::string blackboardKey(const std::string& port_name, const std::string& mapping) {
  if (mapping == "{=}" || mapping == "=") {
    return port_name;
  }
  return std::string(BT::TreeNode::stripBlackboardPointer(mapping));
}

}  // namespace

TreeValidationError::TreeValidationError(std::string code, std::string message)
    : std::runtime_error(std::move(message)), code_(std::move(code)) {}

const std::string& TreeValidationError::code() const noexcept { return code_; }

std::filesystem::path resolveTreePath(const std::filesystem::path& tree_root,
                                      const std::string& task_id) {
  static const std::regex exact_id_pattern(R"(^[A-Za-z0-9][A-Za-z0-9_.@-]*$)");
  if (!std::regex_match(task_id, exact_id_pattern) || task_id == "." || task_id == "..") {
    throw TreeValidationError(
        "supervisor.tree.invalid_id",
        "task_id must be one exact versioned identifier without path separators.");
  }

  auto filename = task_id;
  if (!filename.ends_with(".xml")) {
    filename += ".xml";
  }
  return (tree_root / filename).lexically_normal();
}

BT::Tree createValidatedTreeFromText(BT::BehaviorTreeFactory& factory, const std::string& xml,
                                     const BT::Blackboard::Ptr& blackboard) {
  try {
    std::unordered_map<std::string, BT::NodeType> registered_nodes;
    for (const auto& [name, manifest] : factory.manifests()) {
      registered_nodes.emplace(name, manifest.type);
    }
    BT::VerifyXML(xml, registered_nodes);
    auto tree = factory.createTreeFromText(xml, blackboard);
    validateTreePorts(tree);
    return tree;
  } catch (const TreeValidationError&) {
    throw;
  } catch (const std::exception& error) {
    throw TreeValidationError("supervisor.tree.invalid_xml", error.what());
  }
}

BT::Tree createValidatedTreeFromFile(BT::BehaviorTreeFactory& factory,
                                     const std::filesystem::path& path,
                                     const BT::Blackboard::Ptr& blackboard) {
  std::ifstream input(path);
  if (!input) {
    throw TreeValidationError("supervisor.tree.not_found",
                              "Behavior-tree XML does not exist: " + path.string());
  }
  std::ostringstream xml;
  xml << input.rdbuf();
  if (!input.good() && !input.eof()) {
    throw TreeValidationError("supervisor.tree.read_failed",
                              "Behavior-tree XML could not be read: " + path.string());
  }
  return createValidatedTreeFromText(factory, xml.str(), blackboard);
}

void validateTreePorts(const BT::Tree& tree) {
  std::unordered_set<std::string> produced_keys;
  for (const auto& subtree : tree.subtrees) {
    for (const auto& node : subtree->nodes) {
      const BT::TreeNode* const tree_node = node.get();
      const auto& node_config = tree_node->config();
      for (const auto& [port_name, mapping] : node_config.output_ports) {
        if (BT::TreeNode::isBlackboardPointer(mapping)) {
          produced_keys.insert(blackboardKey(port_name, mapping));
        }
      }
    }
  }

  for (const auto& subtree : tree.subtrees) {
    for (const auto& node : subtree->nodes) {
      const BT::TreeNode* const tree_node = node.get();
      const auto& node_config = tree_node->config();
      const auto* manifest = node_config.manifest;
      if (manifest == nullptr) {
        continue;
      }
      for (const auto& [port_name, port_info] : manifest->ports) {
        if (port_info.direction() == BT::PortDirection::OUTPUT) {
          continue;
        }
        const auto mapping = node_config.input_ports.find(port_name);
        if (mapping == node_config.input_ports.end()) {
          if (port_info.defaultValue().empty()) {
            throw TreeValidationError("supervisor.tree.missing_port",
                                      "Node '" + node->fullPath() +
                                          "' is missing required input port '" + port_name + "'.");
          }
          continue;
        }
        if (!BT::TreeNode::isBlackboardPointer(mapping->second)) {
          continue;
        }

        const auto key = blackboardKey(port_name, mapping->second);
        const auto entry = node_config.blackboard->getEntry(key);
        const bool has_seeded_value = entry != nullptr && !entry->value.empty();
        if (key.empty() || (!has_seeded_value && !produced_keys.contains(key))) {
          throw TreeValidationError(
              "supervisor.tree.missing_blackboard_input",
              "Node '" + node->fullPath() + "' requires missing blackboard input '" + key + "'.");
        }
      }
    }
  }
}

}  // namespace cellforge_supervisor
