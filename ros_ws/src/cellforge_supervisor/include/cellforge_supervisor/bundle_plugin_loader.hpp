#pragma once

#include <behaviortree_cpp/bt_factory.h>

#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace cellforge_supervisor {

class BundlePluginError : public std::runtime_error {
 public:
  BundlePluginError(const char* code, const std::string& message);

  [[nodiscard]] auto code() const noexcept -> const std::string&;

 private:
  std::string code_;
};

struct LoadedBundlePlugin {
  std::string package;
  std::string library;
  std::filesystem::path node_manifest;
};

auto loadBundleDeclaredPlugins(
    BT::BehaviorTreeFactory& factory, const std::filesystem::path& bundle_manifest_path,
    const std::string& expected_bundle_id) -> std::vector<LoadedBundlePlugin>;

}  // namespace cellforge_supervisor
