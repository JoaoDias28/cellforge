cmake_minimum_required(VERSION 3.16)
project(cellforge_supervisor)

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
find_package(ament_index_cpp REQUIRED)
find_package(behaviortree_cpp REQUIRED)
find_package(cellforge_interfaces REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(std_msgs REQUIRED)

add_library(cellforge_supervisor_core SHARED
  src/bundle_plugin_loader.cpp
  src/supervisor_node.cpp
  src/supervisor_nodes.cpp
  src/tree_validation.cpp
)
target_include_directories(cellforge_supervisor_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(cellforge_supervisor_core
  ament_index_cpp
  behaviortree_cpp
  cellforge_interfaces
  rclcpp
  rclcpp_action
  std_msgs
)
target_link_libraries(cellforge_supervisor_core OpenSSL::Crypto nlohmann_json::nlohmann_json)

add_library(cellforge_supervisor_bt_nodes SHARED src/plugin.cpp)
target_compile_definitions(cellforge_supervisor_bt_nodes PRIVATE BT_PLUGIN_EXPORT)
target_link_libraries(cellforge_supervisor_bt_nodes PRIVATE cellforge_supervisor_core)

add_executable(cellforge_supervisor_node src/main.cpp)
target_link_libraries(cellforge_supervisor_node cellforge_supervisor_core)
ament_target_dependencies(cellforge_supervisor_node
  cellforge_interfaces
  rclcpp
  rclcpp_action
  std_msgs
)

install(TARGETS
  cellforge_supervisor_core
  cellforge_supervisor_bt_nodes
  EXPORT export_cellforge_supervisor
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)
install(TARGETS
  cellforge_supervisor_node
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY config/ DESTINATION share/${PROJECT_NAME}/config)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)

  ament_add_gtest(test_tree_validation test/test_tree_validation.cpp)
  if(TARGET test_tree_validation)
    target_link_libraries(test_tree_validation cellforge_supervisor_core)
  endif()

  ament_add_gtest(test_supervisor_nodes test/test_supervisor_nodes.cpp)
  if(TARGET test_supervisor_nodes)
    target_link_libraries(test_supervisor_nodes cellforge_supervisor_core)
    ament_target_dependencies(test_supervisor_nodes rclcpp rclcpp_action)
  endif()

  ament_add_gtest(test_supervisor_node test/test_supervisor_node.cpp)
  if(TARGET test_supervisor_node)
    target_link_libraries(test_supervisor_node cellforge_supervisor_core)
    ament_target_dependencies(test_supervisor_node rclcpp rclcpp_action)
  endif()
endif()

ament_export_targets(export_cellforge_supervisor HAS_LIBRARY_TARGET)
ament_export_dependencies(
  ament_index_cpp
  behaviortree_cpp
  cellforge_interfaces
  nlohmann_json
  OpenSSL
  rclcpp
  rclcpp_action
)
ament_package()
