"""Start the GreenQuartz world with its orthographic image bridge."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource


def generate_launch_description():
    """Launch Gazebo and bridge the overhead image to ROS 2."""
    package_dir = get_package_share_directory('go2_house_world')
    gazebo_launch = os.path.join(
        get_package_share_directory('ros_gz_sim'), 'launch', 'gz_sim.launch.py')
    bridge_launch = os.path.join(
        package_dir, 'launch', 'top_down_camera_bridge.launch.py')
    world = os.path.join(package_dir, 'worlds', 'greenquartz_bto.sdf')
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(gazebo_launch),
            launch_arguments={'gz_args': f'{world} -r'}.items(),
        ),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(bridge_launch)),
    ])
