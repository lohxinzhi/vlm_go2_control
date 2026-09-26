"""Bridge the GreenQuartz overhead camera image from Gazebo to ROS 2."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    """Start a one-way bridge for the overhead camera image."""
    package_dir = get_package_share_directory('go2_house_world')
    config_file = os.path.join(
        package_dir, 'params', 'top_down_camera_bridge.yaml')
    return LaunchDescription([
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            name='top_down_camera_bridge',
            parameters=[{'config_file': config_file}],
            output='screen',
        ),
    ])
