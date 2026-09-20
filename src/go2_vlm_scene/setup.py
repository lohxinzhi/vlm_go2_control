from glob import glob
from setuptools import find_packages, setup

setup(
    name='go2_vlm_scene', version='0.1.0', packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/go2_vlm_scene']),
        ('share/go2_vlm_scene', ['package.xml', 'README.md']),
        ('share/go2_vlm_scene/docs', glob('docs/*.md') + glob('docs/*.txt')),
        ('share/go2_vlm_scene/config', glob('config/*.yaml')),
        ('share/go2_vlm_scene/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'], tests_require=['pytest'], zip_safe=True,
    maintainer='Workspace user', maintainer_email='user@localhost.local',
    description='Go2 RGB buffering and scene capture.', license='Apache-2.0',
    entry_points={'console_scripts': [
        'scene_server = go2_vlm_scene.scene_server:main',
        'capture_scene = go2_vlm_scene.capture_cli:main',
        'capture_eval_scene = go2_vlm_scene.evaluation.cli:capture_main',
        'evaluate_scenes = go2_vlm_scene.evaluation.cli:main',
    ]},
)
