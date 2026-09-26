"""Launch the VLM dialogue manager and its action servers."""

from launch import LaunchDescription
import os

from ament_index_python.packages import get_package_share_directory
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'start_dialogue', default_value='true',
            description='Start the dialogue node for topic-based input.'),
        DeclareLaunchArgument('http_port', default_value='8080'),
        DeclareLaunchArgument('world_name', default_value='greenquartz_bto'),
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
        Node(package='vlm_go2_control', executable='goto_room_server',
             output='screen'),
        Node(package='vlm_go2_control', executable='approach_object_server',
             output='screen',
             parameters=[{
                 'client_type': LaunchConfiguration('vlm_client_type'),
                 'vlm_model': LaunchConfiguration('vlm_model'),
             }]),
        Node(package='vlm_go2_control', executable='describe_scene_server',
             output='screen',
             parameters=[{
                 'client_type': LaunchConfiguration('vlm_client_type'),
                 'vlm_model': LaunchConfiguration('vlm_model'),
             }]),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(
            get_package_share_directory('vlm_go2_control'),
            'launch', 'robot_dashboard.launch.py')),
            launch_arguments={
                'http_port': LaunchConfiguration('http_port'),
                'world_name': LaunchConfiguration('world_name'),
            }.items()),
        Node(package='vlm_go2_control', executable='vlm_dialogue_manager',
             output='screen', parameters=[{
                 'use_console_input': False,
                 'client_type': LaunchConfiguration('dialogue_client_type'),
                 'model': LaunchConfiguration('dialogue_text_model'),
             }],
             condition=IfCondition(LaunchConfiguration('start_dialogue'))),
    ])
