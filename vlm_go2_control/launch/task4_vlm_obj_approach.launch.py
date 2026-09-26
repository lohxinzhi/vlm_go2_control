"""Launch the task 4 dialogue manager and its action servers."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'start_dialogue', default_value='true',
            description='Start the dialogue node for topic-based input.'),
        Node(package='vlm_go2_control', executable='goto_room_server',
             output='screen'),
        Node(package='vlm_go2_control', executable='approach_object_server',
             output='screen'),
        Node(package='vlm_go2_control', executable='describe_scene_server',
             output='screen'),
        Node(package='vlm_go2_control', executable='show_img',
             output='screen'),
        Node(package='vlm_go2_control', executable='task4_vlm_obj_approach',
             output='screen', parameters=[{'use_console_input': False}],
             condition=IfCondition(LaunchConfiguration('start_dialogue'))),
    ])
