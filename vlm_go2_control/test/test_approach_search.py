"""Tests for the bounded object search in the approach action server."""

import math
import json
import time
from threading import Event, Lock
from types import SimpleNamespace

from geometry_msgs.msg import Twist
import numpy as np

from vlm_go2_control import approach_object_server


def test_search_stops_within_one_turn(monkeypatch):
    """An unfound object causes one bounded turn and a stopped robot."""
    monkeypatch.setattr(approach_object_server.rclpy, 'ok', lambda: True)
    monkeypatch.setattr(
        approach_object_server, 'Event',
        lambda: SimpleNamespace(wait=lambda _seconds: None))
    server = SimpleNamespace(
        current_yaw=0.0,
        last_odom_received_at=time.monotonic(),
        filtered_cmd=Twist(),
        camera=SimpleNamespace(frame='frame'),
        canceled=lambda _goal: False,
        wait_for_new_frame=lambda _time, _goal: 'frame',
    )
    commands = []
    checks = []

    def publish(command):
        commands.append(command.angular.z)
        if command.angular.z > 0.0:
            server.current_yaw += 0.05
            server.last_odom_received_at = time.monotonic()

    server.velocity_publisher = SimpleNamespace(publish=publish)
    server.ask_vlm = lambda _name, frame: (
        checks.append(frame) or {'found': False})
    goal = SimpleNamespace(publish_feedback=lambda _feedback: None)

    result = approach_object_server.ApproachObjectServer.search_for_object(
        server, 'cube', goal)

    assert result is None
    assert 0.0 < server.current_yaw < 2.0 * math.pi
    assert 1 <= len(checks) <= 12
    assert commands[-1] == 0.0
    assert all(command >= 0.0 for command in commands)


def test_not_found_is_reported_after_one_search():
    """The action reports not found when its single search finds nothing."""
    searched = []
    published = []
    goal = SimpleNamespace(
        request=SimpleNamespace(object_name='cube'),
        is_cancel_requested=False,
        abort=lambda: searched.append('aborted'))
    server = SimpleNamespace(
        stop_requested=Event(),
        camera=SimpleNamespace(frame='frame', front_distance=3.0),
        filtered_cmd=Twist(),
        velocity_publisher=SimpleNamespace(publish=published.append),
        ask_vlm=lambda _name, _frame: {'found': False},
        search_for_object=lambda _name, _goal: searched.append('search') or None,
        canceled=lambda _goal: False,
        goal_lock=Lock(),
        busy=True,
    )

    result = approach_object_server.ApproachObjectServer.execute(server, goal)

    assert not result.success
    assert 'could not find the cube' in result.message
    assert searched == ['search', 'aborted']
    assert published[-1].linear.x == 0.0
    assert not server.busy


def test_search_detection_continues_approach():
    """An object found during the turn is used by the approach loop."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    finished = []
    goal = SimpleNamespace(
        request=SimpleNamespace(object_name='cube'),
        is_cancel_requested=False,
        succeed=lambda: finished.append('succeeded'))
    server = SimpleNamespace(
        client_type='openai',
        stop_requested=Event(),
        camera=SimpleNamespace(frame=frame, front_distance=1.5),
        filtered_cmd=Twist(),
        velocity_publisher=SimpleNamespace(publish=lambda _command: None),
        ask_vlm=lambda _name, _frame: {'found': False},
        search_for_object=lambda _name, _goal: (
            {'found': True, 'bbox': [40, 30, 60, 70]}, frame),
        canceled=lambda _goal: False,
        publish_bbox=lambda _bbox: None,
        goal_lock=Lock(),
        busy=True,
    )

    result = approach_object_server.ApproachObjectServer.execute(server, goal)

    assert result.success
    assert 'next to the cube' in result.message
    assert finished == ['succeeded']


def test_qwen_pixel_bbox_approaches_object():
    """The approach loop consumes the pixel bbox returned by ask_vlm."""
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    published = []
    goal = SimpleNamespace(
        request=SimpleNamespace(object_name='cube'),
        is_cancel_requested=False,
        succeed=lambda: None)
    server = SimpleNamespace(
        client_type='qwen',
        stop_requested=Event(),
        camera=SimpleNamespace(frame=frame, front_distance=1.5),
        filtered_cmd=Twist(),
        velocity_publisher=SimpleNamespace(publish=lambda _command: None),
        ask_vlm=lambda _name, _frame: {
            'found': True, 'bbox': [80, 40, 120, 60]},
        publish_bbox=published.append,
        goal_lock=Lock(),
        busy=True,
    )

    result = approach_object_server.ApproachObjectServer.execute(server, goal)

    assert result.success
    assert published == [(80.0, 40.0, 120.0, 60.0)]


def test_qwen_detection_saves_annotated_jpeg_only_when_found(
        monkeypatch, tmp_path):
    """Successful detections save pixel-scaled boxes as timestamped JPEGs."""
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    labels = []
    original_put_text = approach_object_server.cv2.putText

    def capture_label(image, text, *args, **kwargs):
        labels.append(text)
        return original_put_text(image, text, *args, **kwargs)

    monkeypatch.setattr(approach_object_server.cv2, 'putText', capture_label)
    responses = iter((
        {'found': True, 'bbox': [400, 400, 600, 600]},
        {'found': False, 'bbox': []},
    ))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=json.dumps(next(responses))))]))))
    server = SimpleNamespace(
        client_type='qwen', client=client, vlm_model='test')
    server.save_detection_image = lambda image, name, bbox: (
        approach_object_server.ApproachObjectServer.save_detection_image(
            server, image, name, bbox))
    monkeypatch.setattr(approach_object_server, 'IMAGE_DIR', tmp_path / 'image')

    found = approach_object_server.ApproachObjectServer.ask_vlm(
        server, 'red cube', frame)
    not_found = approach_object_server.ApproachObjectServer.ask_vlm(
        server, 'red cube', frame)

    saved_images = list((tmp_path / 'image').glob('*.jpg'))
    assert found['bbox'] == [80.0, 40.0, 120.0, 60.0]
    assert not_found['found'] is False
    assert len(saved_images) == 1
    assert 'red_cube' in saved_images[0].name
    assert 'test' in saved_images[0].name
    assert 'Model: test' in labels
    assert approach_object_server.cv2.imread(str(saved_images[0])) is not None
