cmake_minimum_required(VERSION 3.16)
project(cellforge_pen_bt_nodes)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 20)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(WIN32)
  set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
endif()

find_package(ament_cmake REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(cellforge_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)

add_library(cellforge_pen_bt_nodes SHARED
  src/pen_nodes.cpp
  src/plugin.cpp
)
target_compile_definitions(cellforge_pen_bt_nodes PRIVATE BT_PLUGIN_EXPORT)
target_include_directories(cellforge_pen_bt_nodes PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(cellforge_pen_bt_nodes
  behaviortree_cpp
  cellforge_interfaces
  geometry_msgs
  rclcpp
  rclcpp_action
)
target_link_libraries(cellforge_pen_bt_nodes nlohmann_json::nlohmann_json)

install(TARGETS cellforge_pen_bt_nodes
  EXPORT export_cellforge_pen_bt_nodes
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)
install(DIRECTORY include/ DESTINATION include)
install(FILES
  ../../../examples/pen_engraving/behavior_tree_plugins/cellforge_pen_bt_nodes.json
  DESTINATION share/${PROJECT_NAME}/behavior_tree_plugins
)

if(BUILD_TESTING)
  find_package(ament_cmake_clang_format REQUIRED)
  find_package(ament_cmake_clang_tidy REQUIRED)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(cellforge_supervisor REQUIRED)

  ament_add_gtest(test_pen_nodes test/test_pen_nodes.cpp)
  if(TARGET test_pen_nodes)
    target_link_libraries(test_pen_nodes cellforge_pen_bt_nodes)
    ament_target_dependencies(test_pen_nodes rclcpp rclcpp_action)
  endif()

  ament_add_gtest(test_pen_actions test/test_pen_actions.cpp)
  if(TARGET test_pen_actions)
    target_link_libraries(test_pen_actions cellforge_pen_bt_nodes)
    ament_target_dependencies(test_pen_actions rclcpp rclcpp_action)
  endif()

  ament_add_gtest(test_pen_scenarios test/test_pen_scenarios.cpp)
  if(TARGET test_pen_scenarios)
    target_compile_definitions(test_pen_scenarios PRIVATE
      PEN_TREE_PATH="${CMAKE_CURRENT_SOURCE_DIR}/../../../examples/pen_engraving/behavior_tree.xml"
      PEN_TRACE_EXPECTATIONS_PATH="${CMAKE_CURRENT_SOURCE_DIR}/../../../examples/pen_engraving/runtime_trace_expectations.json"
    )
    target_link_libraries(test_pen_scenarios
      cellforge_pen_bt_nodes
      cellforge_supervisor::cellforge_supervisor_core
      nlohmann_json::nlohmann_json
    )
  endif()

  ament_add_gtest(test_plugin_loading test/test_plugin_loading.cpp)
  if(TARGET test_plugin_loading)
    target_compile_definitions(test_plugin_loading PRIVATE
      PEN_NODE_MANIFEST_PATH="${CMAKE_CURRENT_SOURCE_DIR}/../../../examples/pen_engraving/behavior_tree_plugins/cellforge_pen_bt_nodes.json"
    )
    target_link_libraries(test_plugin_loading
      cellforge_supervisor::cellforge_supervisor_core
      nlohmann_json::nlohmann_json
      OpenSSL::Crypto
    )
  endif()

  ament_clang_format(CONFIG_FILE "${CMAKE_CURRENT_SOURCE_DIR}/../../../.clang-format")
  ament_clang_tidy(${CMAKE_BINARY_DIR} TIMEOUT 600)
endif()

ament_export_targets(export_cellforge_pen_bt_nodes HAS_LIBRARY_TARGET)
ament_export_dependencies(behaviortree_cpp cellforge_interfaces geometry_msgs rclcpp rclcpp_action)
ament_package()
