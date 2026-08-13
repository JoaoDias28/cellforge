cmake_minimum_required(VERSION 3.16)
project(cellforge_motion)

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
find_package(cellforge_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(moveit_task_constructor_core REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(trajectory_msgs REQUIRED)

add_library(cellforge_motion_core SHARED src/motion_service.cpp)
target_include_directories(cellforge_motion_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(cellforge_motion_core geometry_msgs moveit_msgs)

add_library(cellforge_motion_moveit SHARED
  src/moveit_planner.cpp
  src/mtc_task_builder.cpp
)

add_library(cellforge_motion_l0 SHARED src/l0_planner.cpp)
target_include_directories(cellforge_motion_l0 PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(cellforge_motion_l0 cellforge_motion_core)
ament_target_dependencies(cellforge_motion_l0 moveit_msgs)
target_include_directories(cellforge_motion_moveit PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(cellforge_motion_moveit cellforge_motion_core)
ament_target_dependencies(cellforge_motion_moveit
  cellforge_interfaces
  moveit_msgs
  moveit_ros_planning_interface
  moveit_task_constructor_core
  rclcpp
  rclcpp_action
)

add_library(cellforge_motion_node SHARED src/motion_node.cpp)
target_include_directories(cellforge_motion_node PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
target_link_libraries(cellforge_motion_node cellforge_motion_core)
ament_target_dependencies(cellforge_motion_node
  cellforge_interfaces
  rclcpp
  rclcpp_action
  trajectory_msgs
)

add_executable(cellforge_motion_service src/main.cpp)
target_link_libraries(cellforge_motion_service
  cellforge_motion_core
  cellforge_motion_moveit
  cellforge_motion_node
)
ament_target_dependencies(cellforge_motion_service rclcpp)

add_executable(cellforge_l0_motion_service src/l0_main.cpp)
target_link_libraries(cellforge_l0_motion_service
  cellforge_motion_core
  cellforge_motion_l0
  cellforge_motion_node
)
ament_target_dependencies(cellforge_l0_motion_service rclcpp)

install(TARGETS
  cellforge_motion_core
  cellforge_motion_moveit
  cellforge_motion_l0
  cellforge_motion_node
  EXPORT export_cellforge_motion
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)
install(TARGETS
  cellforge_motion_service
  cellforge_l0_motion_service
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY config launch DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_clang_format REQUIRED)
  find_package(ament_cmake_clang_tidy REQUIRED)
  find_package(ament_cmake_gtest REQUIRED)

  ament_add_gtest(test_motion_service test/test_motion_service.cpp)
  if(TARGET test_motion_service)
    target_link_libraries(test_motion_service cellforge_motion_core cellforge_motion_l0)
  endif()

  ament_clang_format(CONFIG_FILE "${CMAKE_CURRENT_SOURCE_DIR}/../../../.clang-format")
  ament_clang_tidy(${CMAKE_BINARY_DIR} TIMEOUT 600)
endif()

ament_export_targets(export_cellforge_motion HAS_LIBRARY_TARGET)
ament_export_dependencies(cellforge_interfaces moveit_msgs rclcpp rclcpp_action)
ament_package()
