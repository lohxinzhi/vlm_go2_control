"""Launch the browser dashboard and the Gazebo top-down image bridge."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('http_port', default_value='8080'),
        DeclareLaunchArgument('world_name', default_value='greenquartz_bto'),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('go2_house_world'),
            'launch', 'top_down_camera_bridge.launch.py'))),
        Node(package='ros_gz_bridge', executable='parameter_bridge',
             name='world_control_bridge', output='screen',
             arguments=[['/world/', LaunchConfiguration('world_name'),
                         '/control@ros_gz_interfaces/srv/ControlWorld']]),
        Node(package='vlm_go2_control', executable='robot_dashboard', output='screen',
             parameters=[{
                 'http_port': ParameterValue(
                     LaunchConfiguration('http_port'), value_type=int),
                 'world_name': LaunchConfiguration('world_name'),
             }]),
    ])
