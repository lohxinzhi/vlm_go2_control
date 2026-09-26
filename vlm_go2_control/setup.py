from glob import glob
import os

from setuptools import find_packages, setup

package_name = 'vlm_go2_control'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml'],),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
        (os.path.join('share', package_name, 'maps'), glob('maps/*')),
        (os.path.join('share', package_name, 'params'), glob('params/*.yaml')),
        (os.path.join('share', package_name, 'rviz'), glob('rviz/*.rviz')),
    ],
    install_requires=[
        'numpy<2',
        'openai>=1.0.0,<3.0.0',
        'opencv-python',
        'pyyaml',
        'setuptools',
    ],
    zip_safe=True,
    maintainer='xinzhi',
    maintainer_email='lxzraizer@gmail.com',
    description='TODO: Package description',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'template_node = vlm_go2_control.template_node:main',
            'simulation_odometry = vlm_go2_control.simulation_odometry:main',
            'set_initial_pose = vlm_go2_control.set_initial_pose:main',
            'vlm_dialogue_manager = vlm_go2_control.vlm_dialogue_manager:main',
            'task4_vlm_obj_approach = vlm_go2_control.vlm_dialogue_manager:main',
            'goto_room_server = vlm_go2_control.goto_room_server:main',
            'approach_object_server = vlm_go2_control.approach_object_server:main',
            'describe_scene_server = vlm_go2_control.describe_scene_server:main',
            'show_img = vlm_go2_control.show_img:main',
        ],
    },
)
