"""Launch the shared apartment and the existing team Go2 simulation stack."""
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    house = get_package_share_directory('go2_house_world')
    team = get_package_share_directory('vlm_go2_control')
    resources = os.path.join(house, 'models')
    inherited = os.environ.get('GZ_SIM_RESOURCE_PATH', '')
    if inherited:
        resources += os.pathsep + inherited
    return LaunchDescription([
        DeclareLaunchArgument('gui', default_value='true'),
        DeclareLaunchArgument('use_sim_time', default_value='true'),
        DeclareLaunchArgument('robot_name', default_value='go2'),
        # Shared living-room spawn, preserved from the working apartment launcher.
        DeclareLaunchArgument('world_init_x', default_value='3.10'),
        DeclareLaunchArgument('world_init_y', default_value='4.40'),
        DeclareLaunchArgument('world_init_z', default_value='0.375'),
        DeclareLaunchArgument('world_init_heading', default_value='1.5707963267948966'),
        SetEnvironmentVariable('GZ_SIM_RESOURCE_PATH', resources),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(
                team, 'launch', 'go2_simulation_launch.py')),
            launch_arguments={
                'world': os.path.join(house, 'worlds', 'greenquartz_bto.sdf'),
                'ground_height': '0.0',
                **{name: LaunchConfiguration(name) for name in (
                    'gui', 'use_sim_time', 'robot_name', 'world_init_x',
                    'world_init_y', 'world_init_z', 'world_init_heading')},
            }.items(),
        ),
    ])
