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
        DeclareLaunchArgument(
            'world_name', default_value='greenquartz_bto',
            description='Gazebo world controlled by the dashboard.'),
        DeclareLaunchArgument(
            'vlm_client_type', default_value='openai',
            description='Client backend for the approach_object_server.'),
        DeclareLaunchArgument(
            'vlm_model', default_value='gpt-5-mini',
            description='Vision model used by the approach_object_server.'),
        DeclareLaunchArgument(
            'dialogue_client_type', default_value='openai',
            description='Client backend for the vlm_dialogue_manager.'),
        DeclareLaunchArgument(
            'dialogue_text_model', default_value='gpt-5-mini',
            description='Language model used by the vlm_dialogue_manager.'),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(dialogue_launch),
            launch_arguments={
                'start_dialogue': 'true',
                'http_port': LaunchConfiguration('http_port'),
                'world_name': LaunchConfiguration('world_name'),
                'vlm_client_type': LaunchConfiguration('vlm_client_type'),
                'vlm_model': LaunchConfiguration('vlm_model'),
                'dialogue_client_type': LaunchConfiguration('dialogue_client_type'),
                'dialogue_text_model': LaunchConfiguration('dialogue_text_model'),
            }.items(),
        ),
    ])
