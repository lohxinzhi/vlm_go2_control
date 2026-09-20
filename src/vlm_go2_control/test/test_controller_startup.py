# Copyright 2026 Xinzhi
# SPDX-License-Identifier: Apache-2.0

"""Inspect controller scheduling offline without starting processes or DDS."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from launch import LaunchContext
from launch.actions import OpaqueFunction, TimerAction


def test_reference_controller_startup_timing(monkeypatch):
    """Keep independent 20/30-second spawners and the existing parameter wiring."""
    path = Path(__file__).resolve().parents[1] / 'launch/go2_simulation_launch.py'
    spec = importlib.util.spec_from_file_location('team_simulation_launch', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    nodes = []

    def node(**kwargs):
        action = OpaqueFunction(function=lambda context: [])
        action.test_arguments = kwargs
        nodes.append(action)
        return action

    monkeypatch.setattr(module, 'Node', node)
    monkeypatch.setattr(module, 'get_package_share_directory', lambda name: '/share/' + name)
    monkeypatch.setattr(module.xacro, 'process_file', lambda path: SimpleNamespace(
        toxml=lambda: '<robot><plugin name="gz::sim::systems::OdometryPublisher"/></robot>'))
    description = module.generate_launch_description()
    timers = [action for action in description.entities if isinstance(action, TimerAction)]
    context = LaunchContext()
    context.launch_configurations['use_sim_time'] = 'true'
    scheduled = {}
    for timer in timers:
        delay = float(timer.period)
        for action in timer.actions:
            args = getattr(action, 'test_arguments', {})
            if args.get('package') == 'controller_manager':
                assert args['executable'] == 'spawner'
                assert args['arguments'][1:] == ['--controller-manager-timeout', '120']
                assert args['output'] == 'screen'
                assert len(args['parameters']) == 1
                clock = args['parameters'][0]
                assert set(clock) == {'use_sim_time'}
                assert clock['use_sim_time'].perform(context) == 'true'
                name = args['arguments'][0]
                assert name not in scheduled
                scheduled[name] = delay
    assert scheduled == {
        'joint_states_controller': 20.0,
        'joint_group_effort_controller': 30.0,
    }
    spawners = [n for n in nodes if n.test_arguments['package'] == 'controller_manager']
    assert len(spawners) == 2
    assert all(n not in description.entities for n in spawners)
    champ = next(n.test_arguments for n in nodes if n.test_arguments['package'] == 'champ_base')
    assert champ['parameters'][1:4] == [
        '/share/unitree_go2_sim/config/' + name + '/' + name + '.yaml'
        for name in ('joints', 'links', 'gait')
    ]
    assert champ['parameters'][4]['publish_joint_states'] is False
    assert champ['parameters'][4]['joint_controller_topic'] == (
        'joint_group_effort_controller/joint_trajectory')
    odom = next(n.test_arguments for n in nodes
                if n.test_arguments['package'] == 'vlm_go2_control')
    assert odom['parameters'][0] == '/share/vlm_go2_control/params/go2_odom.yaml'
