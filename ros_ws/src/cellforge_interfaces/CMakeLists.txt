cmake_minimum_required(VERSION 3.16)
project(cellforge_interfaces)

find_package(ament_cmake REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/DeviceState.msg"
  "msg/PoseEstimate.msg"
  "msg/SafetyState.msg"
  "msg/CellState.msg"
  "msg/JobEvent.msg"
  "srv/GetDeviceState.srv"
  "srv/SetDiscreteOutput.srv"
  "srv/ValidateRecipe.srv"
  "action/ExecuteProcess.action"
  "action/ExecuteSkill.action"
  "action/InspectObject.action"
  "action/LocateObject.action"
  "action/RunJob.action"
  DEPENDENCIES builtin_interfaces geometry_msgs std_msgs
)

if(BUILD_TESTING)
  find_package(action_msgs REQUIRED)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)

  ament_add_gtest(test_generated_cpp_types test/test_generated_cpp_types.cpp)
  if(TARGET test_generated_cpp_types)
    rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} "rosidl_typesupport_cpp")
    target_link_libraries(test_generated_cpp_types "${cpp_typesupport_target}")
    ament_target_dependencies(test_generated_cpp_types action_msgs)
  endif()

  ament_add_pytest_test(test_generated_python_types test/test_generated_python_types.py
    APPEND_ENV "PYTHONPATH=${CMAKE_CURRENT_BINARY_DIR}/rosidl_generator_py:$ENV{PYTHONPATH}"
  )
endif()

ament_export_dependencies(rosidl_default_runtime)
ament_package()
