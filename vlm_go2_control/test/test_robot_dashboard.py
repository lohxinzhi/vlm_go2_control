"""Exercise browser requests against the dashboard and local ROS interfaces."""

from http.client import HTTPConnection
import json
from threading import Thread
import time

import cv2
import numpy as np
import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import SetBool

from vlm_go2_control.robot_dashboard import RobotDashboard


@pytest.fixture
def dashboard():
    rclpy.init(args=['--ros-args', '-p', 'http_port:=0'])
    node = RobotDashboard()
    peer = Node('dashboard_test_peer')
    requests = []
    peer.create_subscription(
        String, '/vlm/user_request', lambda msg: requests.append(msg.data), 10)
    replies = peer.create_publisher(String, '/vlm/reply', 10)

    def manual(_request, response):
        response.success = True
        return response

    peer.create_service(SetBool, '/vlm/manual_control', manual)
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    executor.add_node(peer)
    thread = Thread(target=executor.spin)
    thread.start()
    try:
        deadline = time.monotonic() + 3.0
        while node.request_publisher.get_subscription_count() < 2:
            assert time.monotonic() < deadline, 'ROS discovery timed out'
            time.sleep(0.02)
        yield node, requests, replies
    finally:
        node.destroy_node()
        executor.shutdown()
        thread.join()
        peer.destroy_node()
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
    node, prompts, replies = dashboard
    assert request(node, 'GET', '/')[0] == 200
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


def test_teleop_requires_control_and_expires(dashboard):
    """Commands require control, expire, and cannot override a newer stop."""
    node, _, _ = dashboard
    command = {'direction': 'forward', 'client_id': 'test', 'sequence': 0}
    assert request(node, 'POST', '/api/teleop', command, authorized=False)[0] == 403
    assert request(node, 'POST', '/api/teleop', command)[0] == 409
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
