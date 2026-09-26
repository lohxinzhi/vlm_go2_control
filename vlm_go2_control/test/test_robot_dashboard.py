"""Exercise browser requests against the dashboard and local ROS interfaces."""

from http.client import HTTPConnection
import json
from threading import Event, Thread
import time

import cv2
import numpy as np
import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.callback_groups import ReentrantCallbackGroup
from controller_manager_msgs.msg import ControllerState
from controller_manager_msgs.srv import ListControllers, SwitchController
from ros_gz_interfaces.srv import ControlWorld
from std_msgs.msg import String
from std_srvs.srv import SetBool

from vlm_go2_control.robot_dashboard import RobotDashboard


@pytest.fixture
def dashboard():
    rclpy.init(args=['--ros-args', '-p', 'http_port:=0'])
    node = RobotDashboard()
    peer = Node('dashboard_test_peer')
    requests = []
    simulation = {
        'world_requests': [], 'switch_requests': [],
        'states': {'joint_states_controller': 'inactive',
                   'joint_group_effort_controller': 'inactive'},
        'switch_success': True,
        'switch_queued': Event(), 'world_started': Event(),
    }
    simulation_callbacks = ReentrantCallbackGroup()
    peer.create_subscription(
        String, '/vlm/user_request', lambda msg: requests.append(msg.data), 10)
    replies = peer.create_publisher(String, '/vlm/reply', 10)

    def manual(_request, response):
        response.success = True
        return response

    peer.create_service(SetBool, '/vlm/manual_control', manual)

    def control_world(request, response):
        paused = request.world_control.pause
        simulation['world_requests'].append(paused)
        if paused:
            simulation['world_started'].clear()
            response.success = True
        else:
            needs_switch = any(state == 'inactive'
                               for state in simulation['states'].values())
            response.success = not needs_switch or simulation['switch_queued'].wait(2.0)
            if response.success:
                simulation['world_started'].set()
        return response

    def list_controllers(_request, response):
        response.controller = [ControllerState(name=name, state=state)
                               for name, state in simulation['states'].items()]
        return response

    def switch_controllers(request, response):
        simulation['switch_requests'].append(list(request.activate_controllers))
        simulation['switch_queued'].set()
        response.ok = (simulation['world_started'].wait(2.0) and
                       simulation['switch_success'])
        if response.ok:
            for name in request.activate_controllers:
                simulation['states'][name] = 'active'
        return response

    peer.create_service(ControlWorld, '/world/greenquartz_bto/control', control_world,
                        callback_group=simulation_callbacks)
    peer.create_service(ListControllers, '/controller_manager/list_controllers',
                        list_controllers, callback_group=simulation_callbacks)
    peer.create_service(SwitchController, '/controller_manager/switch_controller',
                        switch_controllers, callback_group=simulation_callbacks)
    model_nodes = {}
    for name, model in (('vlm_dialogue_manager', 'dialogue-test-model'),
                        ('describe_scene_server', 'vision-test-model'),
                        ('approach_object_server', 'vision-test-model')):
        model_node = Node(name)
        model_node.declare_parameter('model_in_use', model)
        model_nodes[name] = model_node
    simulation['model_nodes'] = model_nodes
    executor = MultiThreadedExecutor(num_threads=6)
    executor.add_node(node)
    executor.add_node(peer)
    for model_node in model_nodes.values():
        executor.add_node(model_node)
    thread = Thread(target=executor.spin)
    thread.start()
    try:
        deadline = time.monotonic() + 3.0
        while node.request_publisher.get_subscription_count() < 2:
            assert time.monotonic() < deadline, 'ROS discovery timed out'
            time.sleep(0.02)
        yield node, requests, replies, simulation
    finally:
        executor.shutdown()
        thread.join()
        node.destroy_node()
        peer.destroy_node()
        for model_node in model_nodes.values():
            model_node.destroy_node()
        rclpy.shutdown()


def request(node, method, path, data=None, authorized=True):
    connection = HTTPConnection('127.0.0.1', node.http_server.server_port, timeout=12)
    headers = {'Content-Type': 'application/json'}
    if authorized:
        headers['X-Control-Token'] = node.http_server.token
    connection.request(method, path, json.dumps(data) if data is not None else None, headers)
    response = connection.getresponse()
    status, body = response.status, response.read()
    connection.close()
    return status, body


def test_camera_and_conversation_http(dashboard):
    """Both images render and conversation messages make a ROS round trip."""
    node, prompts, replies, _ = dashboard
    status, page = request(node, 'GET', '/')
    assert status == 200
    assert b'Dialogue model' in page and b'VLM model' in page
    assert request(node, 'GET', '/camera.jpg')[0] == 503
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    message = node.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
    node.image_callback(message)
    node.top_down_callback(message)
    for path in ('/camera.jpg', '/top-down.jpg'):
        status, data = request(node, 'GET', path)
        assert status == 200
        assert cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR).shape == frame.shape
    assert request(node, 'POST', '/api/chat', {'text': 'What do you see?'})[0] == 200
    deadline = time.monotonic() + 3.0
    while not prompts:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    replies.publish(String(data='A red cube.'))
    while len(node.dashboard_state()['messages']) < 2:
        assert time.monotonic() < deadline
        time.sleep(0.02)
    state = json.loads(request(node, 'GET', '/api/state')[1])
    assert [message['text'] for message in state['messages']] == [
        'What do you see?', 'A red cube.']


def test_dashboard_reads_models_from_running_nodes(dashboard):
    """Show one VLM model only while both vision nodes report the same one."""
    node, _, _, simulation = dashboard
    deadline = time.monotonic() + 4.0
    while True:
        state = json.loads(request(node, 'GET', '/api/state')[1])
        if (state['dialogue_model'] == 'dialogue-test-model' and
                state['vlm_model'] == 'vision-test-model'):
            break
        assert time.monotonic() < deadline, state
        time.sleep(0.05)
    approach = simulation['model_nodes']['approach_object_server']
    assert approach.set_parameters([
        Parameter('model_in_use', value='another-vision-model')])[0].successful
    deadline = time.monotonic() + 4.0
    while True:
        state = json.loads(request(node, 'GET', '/api/state')[1])
        if state['vlm_model_mismatch']:
            break
        assert time.monotonic() < deadline, state
        time.sleep(0.05)
    assert state['vlm_model'] is None


def test_teleop_requires_control_and_expires(dashboard):
    """Commands require control, expire, and cannot override a newer stop."""
    node, _, _, _ = dashboard
    command = {'direction': 'forward', 'client_id': 'test', 'sequence': 0}
    assert request(node, 'POST', '/api/teleop', command, authorized=False)[0] == 403
    assert request(node, 'POST', '/api/teleop', command)[0] == 409
    assert request(node, 'POST', '/api/simulation/start', {})[0] == 200
    assert request(node, 'POST', '/api/manual', {'enabled': True})[0] == 200
    command['sequence'] = 1
    assert request(node, 'POST', '/api/teleop', command)[0] == 200
    assert node.teleop_command.linear.x > 0
    with node.state_lock:
        node.teleop_deadline = 0.0
    node.publish_teleop()
    assert not node.teleop_active
    assert node.teleop_command.linear.x == 0
    node.set_direction('stop', 'test', 3)
    node.set_direction('forward', 'test', 2)
    assert not node.teleop_active
    assert request(node, 'POST', '/api/manual', {'enabled': False})[0] == 200
    assert not node.manual_enabled


def test_simulation_start_pause_resume_from_dashboard(dashboard):
    """Dashboard commands change Gazebo state and stop motion on pause."""
    node, _, _, simulation = dashboard
    world_requests = simulation['world_requests']
    assert node.dashboard_state()['simulation_paused']
    assert request(node, 'POST', '/api/simulation/start', {}, authorized=False)[0] == 403
    assert request(node, 'POST', '/api/simulation/start', {})[0] == 200
    assert world_requests == [False]
    assert simulation['switch_requests'] == [
        ['joint_states_controller', 'joint_group_effort_controller']]
    assert node.dashboard_state()['simulation_started']
    assert not node.dashboard_state()['simulation_paused']
    assert request(node, 'POST', '/api/simulation/start', {})[0] == 200
    assert world_requests == [False]
    assert request(node, 'POST', '/api/manual', {'enabled': True})[0] == 200
    command = {'direction': 'forward', 'client_id': 'pause-test', 'sequence': 0}
    assert request(node, 'POST', '/api/teleop', command)[0] == 200
    assert node.teleop_active
    assert request(node, 'POST', '/api/simulation/pause', {}, authorized=False)[0] == 403
    assert request(node, 'POST', '/api/simulation/pause', {})[0] == 200
    assert world_requests == [False, True]
    assert node.dashboard_state()['simulation_paused']
    assert not node.teleop_active
    command['sequence'] = 1
    assert request(node, 'POST', '/api/teleop', command)[0] == 409
    assert request(node, 'POST', '/api/simulation/pause', {})[0] == 200
    assert world_requests == [False, True]
    assert request(node, 'POST', '/api/simulation/start', {})[0] == 200
    assert world_requests == [False, True, False]
    assert len(simulation['switch_requests']) == 1
    assert not node.dashboard_state()['simulation_paused']


def test_activation_failure_repauses_gazebo(dashboard):
    """A failed controller switch leaves the world paused and reports an error."""
    node, _, _, simulation = dashboard
    simulation['switch_success'] = False
    assert request(node, 'POST', '/api/simulation/start', {})[0] == 409
    assert simulation['world_requests'] == [False, True]
    assert node.dashboard_state()['simulation_paused']
