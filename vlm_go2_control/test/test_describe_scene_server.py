"""Tests for the camera frame handling in the scene description service."""

import time
from types import SimpleNamespace

import numpy as np
import pytest
import rclpy
from vlm_go2_interfaces.srv import DescribeScene

from vlm_go2_control import describe_scene_server


@pytest.fixture
def scene_server(monkeypatch):
    """Create a service server with a local, deterministic VLM response."""
    calls = []

    def create_completion(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content='A red cube is on the floor.')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=create_completion)))
    monkeypatch.setattr(describe_scene_server, 'OpenAI', lambda **_: client)
    rclpy.init()
    server = describe_scene_server.DescribeSceneServer()
    yield server, calls
    server.destroy_node()
    rclpy.shutdown()


def test_describes_fresh_frame(scene_server):
    """A fresh image is sent to the VLM and returned to the caller."""
    server, calls = scene_server
    server.frame = np.zeros((8, 8, 3), dtype=np.uint8)
    server.frame_received_at = time.monotonic()

    response = server.describe(DescribeScene.Request(), DescribeScene.Response())

    assert response.success
    assert response.description == 'A red cube is on the floor.'
    assert (calls[0]['messages'][0]['content'][0]['text'] ==
            describe_scene_server.SCENE_DESCRIPTION_PROMPT)
    assert calls[0]['messages'][0]['content'][1]['image_url']['url'].startswith(
        'data:image/jpeg;base64,')


def test_rejects_missing_and_stale_frames(scene_server):
    """The service avoids querying a scene without a current image."""
    server, calls = scene_server
    missing = server.describe(DescribeScene.Request(), DescribeScene.Response())
    assert not missing.success
    assert 'No camera frame' in missing.message

    server.frame = np.zeros((8, 8, 3), dtype=np.uint8)
    server.frame_received_at = time.monotonic() - 10.0
    stale = server.describe(DescribeScene.Request(), DescribeScene.Response())
    assert not stale.success
    assert 'stale' in stale.message
    assert not calls


def test_answers_visual_question(scene_server):
    """A specific question selects the VQA prompt and preserves its wording."""
    server, calls = scene_server
    server.frame = np.zeros((8, 8, 3), dtype=np.uint8)
    server.frame_received_at = time.monotonic()
    request = DescribeScene.Request()
    request.mode = 'vqa'
    request.question = 'What colour is the cube?'

    response = server.describe(request, DescribeScene.Response())

    assert response.success
    prompt = calls[0]['messages'][0]['content'][0]['text']
    assert describe_scene_server.VISUAL_VQA_PROMPT in prompt
    assert '"What colour is the cube?"' in prompt


def test_rejects_invalid_visual_requests(scene_server):
    """Invalid modes and missing questions do not invoke the VLM."""
    server, calls = scene_server
    request = DescribeScene.Request()
    request.mode = 'vqa'
    missing_question = server.describe(request, DescribeScene.Response())
    assert not missing_question.success
    assert 'question is required' in missing_question.message

    request.mode = 'describe'
    request.question = 'What is on the floor?'
    mismatched_mode = server.describe(request, DescribeScene.Response())
    assert not mismatched_mode.success
    assert 'requires vqa mode' in mismatched_mode.message
    assert not calls
