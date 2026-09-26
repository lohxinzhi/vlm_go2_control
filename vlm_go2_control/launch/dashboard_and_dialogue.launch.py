"""Start the robot dashboard and VLM dialogue manager together."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    """Include the dialogue stack, dashboard, and top-down camera bridge."""
    package_dir = get_package_share_directory('vlm_go2_control')
    dialogue_launch = os.path.join(
        package_dir, 'launch', 'vlm_dialogue_manager.launch.py')
    return LaunchDescription([
        DeclareLaunchArgument(
            'http_port', default_value='8080',
            description='Local HTTP port for the robot dashboard.'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(dialogue_launch),
            launch_arguments={
                'start_dialogue': 'true',
                'http_port': LaunchConfiguration('http_port'),
            }.items(),
        ),
    ])
