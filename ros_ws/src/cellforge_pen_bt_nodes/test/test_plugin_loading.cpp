#include <gtest/gtest.h>
#include <openssl/evp.h>

#include <array>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <memory>
#include <nlohmann/json.hpp>
#include <sstream>
#include <string>

#include "cellforge_supervisor/bundle_plugin_loader.hpp"

namespace cellforge_pen_bt_nodes {
namespace {

using Json = nlohmann::json;

auto readFile(const std::filesystem::path& path) -> std::string {
  std::ifstream input(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}

auto sha256(const std::string& value) -> std::string {
  auto context =
      std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  EXPECT_NE(context, nullptr);
  EXPECT_EQ(EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr), 1);
  EXPECT_EQ(EVP_DigestUpdate(context.get(), value.data(), value.size()), 1);
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int length = 0;
  EXPECT_EQ(EVP_DigestFinal_ex(context.get(), digest.data(), &length), 1);
  std::ostringstream output;
  output << std::hex << std::setfill('0');
  for (std::size_t index = 0; index < length; ++index) {
    output << std::setw(2) << static_cast<unsigned int>(digest[index]);
  }
  return output.str();
}

auto writeBundle(const std::filesystem::path& root, const std::string& digest,
                 bool declare_native = true) -> std::filesystem::path {
  const auto path = root / "manifest.json";
  const Json manifest = {
      {"bundle_id", std::string(64, 'a')},
      {"native_packages", declare_native ? Json::array({"cellforge_pen_bt_nodes"}) : Json::array()},
      {"behavior_tree_plugins",
       Json::array({{{"package", "cellforge_pen_bt_nodes"},
                     {"library", "cellforge_pen_bt_nodes"},
                     {"manifest_path", "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json"},
                     {"manifest_sha256", digest}}})},
  };
  std::ofstream(path) << manifest.dump();
  return path;
}

class TemporaryBundle {
 public:
  TemporaryBundle() {
    root_ = std::filesystem::temp_directory_path() /
            ("cellforge-plugin-test-" + std::to_string(++ordinal_));
    std::filesystem::create_directories(root_ / "config/behavior-tree-plugins");
  }
  ~TemporaryBundle() { std::filesystem::remove_all(root_); }
  [[nodiscard]] auto root() const -> const std::filesystem::path& { return root_; }

 private:
  inline static int ordinal_{0};
  std::filesystem::path root_;
};

TEST(BundlePluginLoading, LoadsOnlyTheDigestMatchingBundleDeclaredPackageLibrary) {
  TemporaryBundle bundle;
  const auto content = readFile(PEN_NODE_MANIFEST_PATH);
  const auto frozen = bundle.root() / "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json";
  std::ofstream(frozen, std::ios::binary) << content;
  const auto manifest = writeBundle(bundle.root(), sha256(content));
  BT::BehaviorTreeFactory factory;

  const auto loaded =
      cellforge_supervisor::loadBundleDeclaredPlugins(factory, manifest, std::string(64, 'a'));

  ASSERT_EQ(loaded.size(), 1U);
  EXPECT_EQ(loaded.front().package, "cellforge_pen_bt_nodes");
  EXPECT_TRUE(factory.manifests().contains("ExecuteProcess"));
  EXPECT_TRUE(factory.manifests().contains("RecordProductionResult"));
}

TEST(BundlePluginLoading, RejectsDigestMismatchAndUndeclaredPackageBeforeLoading) {
  TemporaryBundle bundle;
  const auto content = readFile(PEN_NODE_MANIFEST_PATH);
  const auto frozen = bundle.root() / "config/behavior-tree-plugins/cellforge_pen_bt_nodes.json";
  std::ofstream(frozen, std::ios::binary) << content;

  BT::BehaviorTreeFactory digest_factory;
  EXPECT_THROW(
      cellforge_supervisor::loadBundleDeclaredPlugins(
          digest_factory, writeBundle(bundle.root(), std::string(64, '0')), std::string(64, 'a')),
      cellforge_supervisor::BundlePluginError);

  BT::BehaviorTreeFactory package_factory;
  EXPECT_THROW(cellforge_supervisor::loadBundleDeclaredPlugins(
                   package_factory, writeBundle(bundle.root(), sha256(content), false),
                   std::string(64, 'a')),
               cellforge_supervisor::BundlePluginError);
}

}  // namespace
}  // namespace cellforge_pen_bt_nodes
