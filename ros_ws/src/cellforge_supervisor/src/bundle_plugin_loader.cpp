#include "cellforge_supervisor/bundle_plugin_loader.hpp"

#include <openssl/evp.h>

#include <ament_index_cpp/get_package_prefix.hpp>
#include <array>
#include <fstream>
#include <memory>
#include <nlohmann/json.hpp>
#include <regex>
#include <set>
#include <sstream>
#include <string_view>

namespace cellforge_supervisor {
namespace {

using Json = nlohmann::json;

struct PluginIdentity {
  std::string package;
  std::string library;
};

auto readFile(const std::filesystem::path& path) -> std::string {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw BundlePluginError("supervisor.plugin.file_unavailable",
                            "Immutable plugin file is unavailable: " + path.string());
  }
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

auto sha256(const std::string& value) -> std::string {
  auto context =
      std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)>(EVP_MD_CTX_new(), EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1 ||
      EVP_DigestUpdate(context.get(), value.data(), value.size()) != 1) {
    throw BundlePluginError("supervisor.plugin.digest_failed",
                            "Could not initialize plugin-manifest SHA-256 validation.");
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int digest_length = 0;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &digest_length) != 1) {
    throw BundlePluginError("supervisor.plugin.digest_failed",
                            "Could not finalize plugin-manifest SHA-256 validation.");
  }
  static constexpr std::string_view kHex = "0123456789abcdef";
  static constexpr auto kLowNibbleMask = 0x0FU;
  std::string output(static_cast<std::size_t>(digest_length) * 2U, '0');
  for (std::size_t index = 0; index < digest_length; ++index) {
    output[index * 2U] = kHex[digest[index] >> 4U];
    output[index * 2U + 1U] = kHex[digest[index] & kLowNibbleMask];
  }
  return output;
}

auto requiredString(const Json& object, const char* key) -> std::string {
  if (!object.contains(key) || !object.at(key).is_string() ||
      object.at(key).get_ref<const std::string&>().empty()) {
    throw BundlePluginError("supervisor.plugin.manifest_invalid",
                            std::string("Plugin declaration requires string '") + key + "'.");
  }
  return object.at(key).get<std::string>();
}

void requireIdentifier(const std::string& value, const char* field) {
  static const std::regex identifier(R"(^[A-Za-z0-9][A-Za-z0-9_.-]*$)");
  if (!std::regex_match(value, identifier)) {
    throw BundlePluginError("supervisor.plugin.manifest_invalid",
                            std::string("Plugin ") + field + " is not a stable identifier.");
  }
}

auto containedPath(const std::filesystem::path& root,
                   const std::string& reference)
    -> std::filesystem::path {
  const auto raw = std::filesystem::path(reference);
  const auto normalized_root = std::filesystem::weakly_canonical(root);
  const auto candidate = std::filesystem::weakly_canonical(normalized_root / raw);
  const auto relative = candidate.lexically_relative(normalized_root);
  if (raw.is_absolute() || relative.empty() || *relative.begin() == "..") {
    throw BundlePluginError("supervisor.plugin.path_invalid",
                            "Plugin node manifest escapes the immutable bundle root.");
  }
  return candidate;
}

auto declaredNodeTypes(const std::string& manifest_text, const PluginIdentity& identity)
    -> std::set<std::string> {
  Json document;
  try {
    document = Json::parse(manifest_text);
  } catch (const Json::exception& error) {
    throw BundlePluginError("supervisor.plugin.node_manifest_invalid", error.what());
  }
  if (document.value("schema_version", "") != "0.1.0" || !document.contains("plugin") ||
      !document.at("plugin").is_object() || !document.contains("nodes") ||
      !document.at("nodes").is_array() ||
      document.at("plugin").value("package", "") != identity.package ||
      document.at("plugin").value("library", "") != identity.library) {
    throw BundlePluginError("supervisor.plugin.node_manifest_invalid",
                            "Node manifest identity does not match the bundle declaration.");
  }
  std::set<std::string> nodes;
  for (const auto& node : document.at("nodes")) {
    if (!node.is_object() || !node.contains("type") || !node.at("type").is_string() ||
        !nodes.insert(node.at("type").get<std::string>()).second) {
      throw BundlePluginError("supervisor.plugin.node_manifest_invalid",
                              "Node manifest contains an invalid or duplicate type.");
    }
  }
  return nodes;
}

auto pluginLibraryPath(const PluginIdentity& identity) -> std::filesystem::path {
  const auto prefix = std::filesystem::path(ament_index_cpp::get_package_prefix(identity.package));
#ifdef _WIN32
  const auto filename = identity.library + ".dll";
  const auto candidate = prefix / "bin" / filename;
#elif __APPLE__
  const auto filename = "lib" + identity.library + ".dylib";
  const auto candidate = prefix / "lib" / filename;
#else
  const auto filename = "lib" + identity.library + ".so";
  const auto candidate = prefix / "lib" / filename;
#endif
  if (!std::filesystem::is_regular_file(candidate)) {
    throw BundlePluginError(
        "supervisor.plugin.library_unavailable",
        "Declared plugin library is unavailable beneath package prefix: " + candidate.string());
  }
  return candidate;
}

auto loadDeclaration(BT::BehaviorTreeFactory& factory, const Json& declaration,
                     const std::filesystem::path& bundle_root,
                     const std::set<std::string>& native_packages, std::set<std::string>& packages)
    -> LoadedBundlePlugin {
  if (!declaration.is_object()) {
    throw BundlePluginError("supervisor.plugin.manifest_invalid",
                            "Plugin declaration must be an object.");
  }
  const PluginIdentity identity{requiredString(declaration, "package"),
                                requiredString(declaration, "library")};
  const auto manifest_reference = requiredString(declaration, "manifest_path");
  const auto expected_digest = requiredString(declaration, "manifest_sha256");
  requireIdentifier(identity.package, "package");
  requireIdentifier(identity.library, "library");
  if (!packages.insert(identity.package).second || !native_packages.contains(identity.package)) {
    throw BundlePluginError("supervisor.plugin.package_undeclared",
                            "Plugin package is duplicate or absent from native_packages.");
  }
  const auto node_manifest = containedPath(bundle_root, manifest_reference);
  const auto node_manifest_text = readFile(node_manifest);
  if (sha256(node_manifest_text) != expected_digest) {
    throw BundlePluginError("supervisor.plugin.digest_mismatch",
                            "Plugin node manifest does not match its immutable digest.");
  }
  const auto expected_nodes = declaredNodeTypes(node_manifest_text, identity);
  const auto before = factory.manifests();
  factory.registerFromPlugin(pluginLibraryPath(identity).string());
  std::set<std::string> registered_nodes;
  for (const auto& [node_type, unused] : factory.manifests()) {
    (void)unused;
    if (!before.contains(node_type)) {
      registered_nodes.insert(node_type);
    }
  }
  if (registered_nodes != expected_nodes) {
    throw BundlePluginError("supervisor.plugin.registration_mismatch",
                            "Loaded plugin registrations do not match its node manifest.");
  }
  return {identity.package, identity.library, node_manifest};
}

}  // namespace

BundlePluginError::BundlePluginError(const char* code, const std::string& message)
    : std::runtime_error(message), code_(code) {}

auto BundlePluginError::code() const noexcept -> const std::string& { return code_; }

auto loadBundleDeclaredPlugins(BT::BehaviorTreeFactory& factory,
                               const std::filesystem::path& bundle_manifest_path,
                               const std::string& expected_bundle_id)
    -> std::vector<LoadedBundlePlugin> {
  Json bundle;
  try {
    bundle = Json::parse(readFile(bundle_manifest_path));
  } catch (const BundlePluginError&) {
    throw;
  } catch (const Json::exception& error) {
    throw BundlePluginError("supervisor.plugin.bundle_manifest_invalid", error.what());
  }
  if (!bundle.is_object() || !bundle.contains("behavior_tree_plugins") ||
      !bundle.at("behavior_tree_plugins").is_array()) {
    throw BundlePluginError("supervisor.plugin.bundle_manifest_invalid",
                            "Bundle manifest has no behavior_tree_plugins array.");
  }
  if (!expected_bundle_id.empty() && bundle.value("bundle_id", "") != expected_bundle_id) {
    throw BundlePluginError("supervisor.plugin.bundle_identity_mismatch",
                            "Plugin declaration belongs to a different active bundle.");
  }
  std::set<std::string> native_packages;
  if (bundle.contains("native_packages") && bundle.at("native_packages").is_array()) {
    for (const auto& package : bundle.at("native_packages")) {
      if (package.is_string()) {
        native_packages.insert(package.get<std::string>());
      }
    }
  }
  const auto bundle_root = std::filesystem::weakly_canonical(bundle_manifest_path.parent_path());
  std::vector<LoadedBundlePlugin> loaded;
  std::set<std::string> packages;
  for (const auto& declaration : bundle.at("behavior_tree_plugins")) {
    loaded.push_back(loadDeclaration(factory, declaration, bundle_root, native_packages, packages));
  }
  return loaded;
}

}  // namespace cellforge_supervisor
