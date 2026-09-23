from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from pathlib import Path


def generate_launch_description():
    config = str(Path(get_package_share_directory('go2_vlm_scene')) / 'config/scene.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('config', default_value=config),
        DeclareLaunchArgument('runtime_data_directory', default_value='.runtime/go2_vlm_scene'),
        Node(package='go2_vlm_scene', executable='scene_server', name='scene_server',
             output='screen', parameters=[LaunchConfiguration('config'), {
                 'runtime_data_directory': LaunchConfiguration('runtime_data_directory'),
             }]),
    ])
