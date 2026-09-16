# Copyright 2026 Xinzhi
# SPDX-License-Identifier: Apache-2.0

"""Run Go2 with CHAMP odometry and a single publisher for each TF edge."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Reuse upstream models and controllers with navigation-compatible wiring."""
    package_dir = get_package_share_directory('vlm_go2_control')
    sim_dir = get_package_share_directory('unitree_go2_sim')
    description_dir = get_package_share_directory('unitree_go2_description')
    model = os.path.join(description_dir, 'urdf', 'unitree_go2_robot.xacro')
    clock = {'use_sim_time': LaunchConfiguration('use_sim_time')}
    urdf = ParameterValue(Command(['xacro ', model]), value_type=str)
    configs = [
        os.path.join(sim_dir, 'config', folder, folder + '.yaml')
        for folder in ('joints', 'links', 'gait')
    ]
    defaults = {
        'use_sim_time': 'true', 'gui': 'true', 'robot_name': 'go2',
        'world': os.path.join(description_dir, 'worlds', 'TIbuilding.sdf'),
        'world_init_x': '0.0', 'world_init_y': '0.0',
        'world_init_z': '4.375', 'world_init_heading': '0.0',
    }
    actions = [
        DeclareLaunchArgument(name, default_value=value)
        for name, value in defaults.items()
    ]
    actions.extend([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')),
            launch_arguments={'gz_args': [
                '"', LaunchConfiguration('world'), '" -r',
                PythonExpression([
                    "' ' if '", LaunchConfiguration('gui'),
                    "'.lower() == 'true' else ' -s'"]),
            ]}.items(),
        ),
        Node(
            package='robot_state_publisher', executable='robot_state_publisher',
            parameters=[clock, {'robot_description': urdf}], output='screen'),
        Node(
            package='ros_gz_sim', executable='create', output='screen',
            arguments=[
                '-name', LaunchConfiguration('robot_name'), '-topic', 'robot_description',
                '-x', LaunchConfiguration('world_init_x'),
                '-y', LaunchConfiguration('world_init_y'),
                '-z', LaunchConfiguration('world_init_z'),
                '-Y', LaunchConfiguration('world_init_heading')]),
        Node(
            package='ros_gz_bridge', executable='parameter_bridge',
            name='gazebo_bridge', output='screen',
            parameters=[clock, {'config_file': os.path.join(
                package_dir, 'params', 'go2_bridge.yaml')}]),
        Node(
            package='champ_base', executable='quadruped_controller_node', output='screen',
            parameters=[clock, *configs, {
                'urdf': urdf, 'gazebo': True, 'publish_joint_states': True,
                'publish_joint_control': True, 'publish_foot_contacts': False,
                'joint_controller_topic': 'joint_group_effort_controller/joint_trajectory',
                'hardware_connected': False, 'close_loop_odom': True,
            }],
            remappings=[('/cmd_vel/smooth', '/cmd_vel')]),
        Node(
            package='champ_base', executable='state_estimation_node', output='screen',
            parameters=[clock, *configs, {'urdf': urdf, 'orientation_from_imu': True}]),
        # These EKFs own odom -> base_footprint -> base_link. SLAM owns map -> odom.
        Node(
            package='robot_localization', executable='ekf_node',
            name='base_to_footprint_ekf', output='screen',
            parameters=[
                os.path.join(get_package_share_directory('champ_base'),
                             'config', 'ekf', 'base_to_footprint.yaml'),
                clock, {'base_link_frame': 'base_link'}],
            remappings=[('odometry/filtered', 'odom/local')]),
        Node(
            package='robot_localization', executable='ekf_node',
            name='footprint_to_odom_ekf', output='screen',
            parameters=[os.path.join(package_dir, 'params', 'go2_odom.yaml'), clock],
            remappings=[('odometry/filtered', 'odom')]),
        # Retain the upstream startup delay while Gazebo creates ros2_control.
        TimerAction(period=20.0, actions=[
            Node(
                package='controller_manager', executable='spawner', output='screen',
                arguments=['joint_states_controller', 'joint_group_effort_controller',
                           '--controller-manager-timeout', '120'],
                parameters=[clock]),
        ]),
    ])
    return LaunchDescription(actions)
