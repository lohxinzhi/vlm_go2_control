# Copyright 2026 Xinzhi
# SPDX-License-Identifier: Apache-2.0

"""Launch the Go2 simulation with Nav2 and online SLAM by default."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PythonExpression


def generate_launch_description():
    """Build the single-robot simulation and navigation launch description."""
    package_dir = get_package_share_directory('vlm_go2_control')
    nav2_dir = get_package_share_directory('nav2_bringup')
    description_dir = get_package_share_directory('unitree_go2_description')
    defaults = {
        'slam': ('true', 'Run online mapping; false uses the supplied map'),
        'map': (os.path.join(nav2_dir, 'maps', 'depot.yaml'), 'Map for slam:=false'),
        'use_sim_time': ('true', 'Use the Gazebo clock'),
        'params_file': (
            os.path.join(package_dir, 'params', 'nav2_go2_params.yaml'),
            'Nav2 and SLAM Toolbox parameters'),
        'autostart': ('true', 'Activate the navigation stack'),
        'use_composition': ('true', 'Compose Nav2 nodes'),
        'use_respawn': ('false', 'Respawn non-composed Nav2 nodes'),
        'use_rviz': ('true', 'Start RViz'),
        'rviz_config_file': (
            os.path.join(package_dir, 'rviz', 'nav2_default_view.rviz'),
            'RViz configuration'),
        'world': (
            os.path.join(description_dir, 'worlds', 'TIbuilding.sdf'),
            'Gazebo world file'),
        'gui': ('true', 'Start the Gazebo GUI'),
        'robot_name': ('go2', 'Gazebo entity name'),
        'world_init_x': ('0.0', 'Spawn x'),
        'world_init_y': ('0.0', 'Spawn y'),
        'world_init_z': ('4.375', 'Spawn z; use 0.375 for default.sdf'),
        'world_init_heading': ('0.0', 'Spawn yaw in radians'),
    }
    actions = [
        DeclareLaunchArgument(name, default_value=value, description=description)
        for name, (value, description) in defaults.items()
    ]
    # The upstream CHAMP and sensor interfaces use absolute topic names.
    actions.extend([
        DeclareLaunchArgument('namespace', default_value='', choices=['']),
        DeclareLaunchArgument('use_namespace', default_value='false', choices=['false']),
    ])
    actions.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(package_dir, 'launch', 'go2_simulation_launch.py')),
        launch_arguments={
            name: LaunchConfiguration(name) for name in (
                'use_sim_time', 'world', 'gui', 'robot_name',
                'world_init_x', 'world_init_y', 'world_init_z', 'world_init_heading')
        }.items(),
    ))
    actions.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav2_dir, 'launch', 'bringup_launch.py')),
        launch_arguments={
            # Nav2's PythonExpression conditions require Python boolean spelling.
            name: (PythonExpression([
                "'", LaunchConfiguration(name), "'.lower() in ('true', '1')"])
                if name in ('slam', 'use_composition') else LaunchConfiguration(name))
            for name in (
                'slam', 'map', 'use_sim_time', 'params_file', 'autostart',
                'use_composition', 'use_respawn', 'namespace', 'use_namespace')
        }.items(),
    ))
    actions.append(IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(nav2_dir, 'launch', 'rviz_launch.py')),
        condition=IfCondition(LaunchConfiguration('use_rviz')),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'rviz_config': LaunchConfiguration('rviz_config_file'),
        }.items(),
    ))
    return LaunchDescription(actions)
