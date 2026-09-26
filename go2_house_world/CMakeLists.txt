cmake_minimum_required(VERSION 3.8)
project(go2_house_world)
find_package(ament_cmake REQUIRED)
find_package(gz-sim8 REQUIRED)
find_package(gz-rendering8 REQUIRED)
find_package(gz-plugin2 REQUIRED COMPONENTS register)

add_library(orthographic_camera_system SHARED src/orthographic_camera_system.cpp)
target_compile_features(orthographic_camera_system PRIVATE cxx_std_17)
target_link_libraries(orthographic_camera_system PRIVATE
  gz-sim8::gz-sim8
  gz-rendering8::gz-rendering8
  gz-plugin2::gz-plugin2)
install(TARGETS orthographic_camera_system
  LIBRARY DESTINATION share/${PROJECT_NAME}/plugins)

install(DIRECTORY models worlds launch params maps DESTINATION share/${PROJECT_NAME})
install(FILES README.md DESTINATION share/${PROJECT_NAME})
if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(world_resources test/test_world_resources.py)
endif()
ament_package()
