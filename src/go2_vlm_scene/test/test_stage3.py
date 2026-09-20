"""Stage 3 service tests use fake providers and the suite-wide network block."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import numpy as np
import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from go2_vlm_interfaces.srv import QueryScene
from go2_vlm_scene.scene_server import SceneServer


def test_stage3_service_followups_and_logs(tmp_path, monkeypatch):
    import openai
    import httpx
    monkeypatch.setenv('OPENAI_API_KEY', 'test-credential-private')
    monkeypatch.setenv('GEMINI_API_KEY', 'test-credential-private')
    factory = MagicMock()
    call = factory.return_value.__enter__.return_value.chat.completions.create
    call.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='The cube is green.'))], usage=None)
    monkeypatch.setattr(openai, 'OpenAI', factory)
    rclpy.init(args=['--ros-args', '-p', 'camera_topic:=/go2_vlm_test/stage3',
        '-p', f'runtime_data_directory:={tmp_path}', '-p', 'enable_external_api_calls:=true',
        '-p', 'retained_scene_count:=2'])
    server = SceneServer()
    client_node = rclpy.create_node('stage3_test_client')
    executor = SingleThreadedExecutor()
    executor.add_node(server)
    executor.add_node(client_node)
    client = client_node.create_client(QueryScene, '/go2_vlm/query')
    def query(**kwargs):
        assert client.wait_for_service(timeout_sec=3)
        future = client.call_async(QueryScene.Request(**kwargs))
        executor.spin_until_future_complete(future, timeout_sec=5)
        assert future.done()
        return future.result()
    try:
        green = np.zeros((20, 30, 3), dtype=np.uint8)
        green[:, :, 1] = 255
        server.buffer.update(green, 1, 2, 'test_camera')
        described = query(mode='describe', provider='openai', refresh_frame=True)
        assert described.success and described.scene_id and described.answer == 'The cube is green.'
        initial = dict(server.last_query_metadata)
        assert described.image_stamp.sec == 1 and described.frame_id == 'test_camera'
        server.buffer.update(np.zeros_like(green), 3, 4, 'new_camera')
        followup = query(mode='vqa', provider='gemini', question='What colour is the cube?', scene_id=described.scene_id)
        assert followup.success and followup.scene_id == described.scene_id
        assert followup.image_stamp.sec == 1 and followup.frame_id == 'test_camera'
        assert server.last_query_metadata['image_jpeg_sha256'] == initial['image_jpeg_sha256']
        assert server.last_query_metadata['prompt_version'] == 'visual-vqa-v1'
        assert described.provider == 'openai' and followup.provider == 'gemini'
        assert followup.model == 'gemini-3.8-flash'
        refreshed = query(mode='vqa', question='What is visible?', scene_id=described.scene_id, refresh_frame=True)
        assert refreshed.success and refreshed.scene_id != described.scene_id
        assert refreshed.image_stamp.sec == 3
        assert server.last_query_metadata['image_jpeg_sha256'] != initial['image_jpeg_sha256']
        count = call.call_count
        for kwargs, error in [
            ({'mode': 'vqa', 'question': ' '}, 'INVALID_REQUEST'),
            ({'mode': 'describe', 'provider': 'other'}, 'INVALID_REQUEST'),
            ({'mode': 'describe', 'provider': 'qwen'}, 'INVALID_REQUEST'),
            ({'mode': 'vqa', 'question': 'test', 'scene_id': 'missing'}, 'SCENE_NOT_FOUND'),
        ]:
            response = query(**kwargs)
            assert not response.success and response.error_message.startswith(error)
        assert call.call_count == count
        server.buffer.capture()  # Evicts the original retained image.
        expired = query(mode='vqa', question='What colour?', scene_id=described.scene_id)
        assert not expired.success and expired.error_message.startswith('SCENE_NOT_FOUND')
        assert call.call_count == count
        error = openai.APIStatusError('Authorization: test-credential-private',
            response=httpx.Response(403, request=httpx.Request('POST', 'https://example.invalid')), body={})
        call.side_effect = error
        failure = query(mode='vqa', question='Authorization: test-credential-private', scene_id=refreshed.scene_id)
        assert not failure.success and failure.error_message.startswith('PROVIDER_ERROR')
        assert call.call_count == count + 1
        logs = [json.loads(line) for line in (tmp_path / 'queries.jsonl').read_text().splitlines()]
        assert len(logs) == 9
        assert logs[0]['response'] == described.answer
        assert logs[0]['question'] == ''
        assert logs[1]['question'] == 'What colour is the cube?'
        assert logs[0]['image_jpeg_sha256'] == logs[1]['image_jpeg_sha256']
        assert logs[1]['scene_id'] == described.scene_id
        assert logs[-1]['attempt_count'] == 1 and logs[-1]['status'] == 'PROVIDER_ERROR'
        assert 'test-credential-private' not in (tmp_path / 'queries.jsonl').read_text()
        assert not any(name == '/cmd_vel' for name, _ in client_node.get_publisher_names_and_types_by_node('scene_server', '/'))
    finally:
        executor.shutdown()
        server.destroy_node()
        client_node.destroy_node()
        rclpy.shutdown()


def test_jsonl_redaction(tmp_path):
    from go2_vlm_scene.query_log import QueryLog
    log = QueryLog(tmp_path, environ={'GEMINI_API_KEY': 'private-value'})
    log.append({'question': 'private-value', 'response': 'Authorization: Bearer another-secret\nFine.',
                'raw_usage': {'authorization': 'another-secret', 'total_tokens': 3}})
    text = (tmp_path / 'queries.jsonl').read_text()
    assert 'private-value' not in text and 'another-secret' not in text
    assert json.loads(text)['raw_usage']['total_tokens'] == 3
