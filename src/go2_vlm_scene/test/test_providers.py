"""All provider tests run with Python network connections forbidden."""
import base64
import json
import socket
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
import cv2
import numpy as np
import pytest
from go2_vlm_scene.camera import CameraBuffer
from go2_vlm_scene.image_encoding import prepare_image, PreparedImage
from go2_vlm_scene.prompts import select_prompt, SCENE_DESCRIPTION_PROMPT, PROMPT_VERSION
from go2_vlm_scene.providers import create_provider
from go2_vlm_scene.providers.config import resolve_config
from go2_vlm_scene.providers.openai_provider import OpenAIProvider
from go2_vlm_scene.providers.qwen_provider import QwenProvider
from go2_vlm_scene.query_pipeline import query_scene
from go2_vlm_scene.types import QueryOptions


@pytest.fixture
def scene():
    buffer = CameraBuffer()
    rgb = np.zeros((480, 640, 3), dtype=np.uint8)
    rgb[:, :320, 0] = 255
    rgb[:, 320:, 2] = 255
    buffer.update(rgb, 10, 20, 'camera_link')
    return buffer.capture()


def fake_factory(usage=None, content='A red cube.'):
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
                               usage=usage)
    factory = MagicMock()
    factory.return_value.__enter__.return_value.chat.completions.create.return_value = response
    return factory


@pytest.mark.parametrize('name,cls', [('openai', OpenAIProvider), ('qwen', QwenProvider)])
def test_provider_selection(name, cls):
    assert isinstance(create_provider(name, environ={'QWEN_BASE_URL': 'https://example.invalid/v1'}), cls)


@pytest.mark.parametrize('name,error', [('', 'MISSING_PROVIDER'), ('other', 'UNKNOWN_PROVIDER')])
def test_missing_unknown_provider(name, error):
    with pytest.raises(ValueError, match=error):
        create_provider(name, environ={})


def test_missing_qwen_endpoint():
    with pytest.raises(ValueError, match='MISSING_QWEN_BASE_URL'):
        resolve_config('qwen', environ={})


@pytest.mark.parametrize('url', ['http://example.invalid/v1', 'https://{WorkspaceId}.invalid/v1',
                               'https://user:password@example.invalid/v1'])
def test_invalid_qwen_endpoint(url):
    with pytest.raises(ValueError, match='INVALID_QWEN_BASE_URL'):
        resolve_config('qwen', environ={'QWEN_BASE_URL': url})


@pytest.mark.parametrize('provider', ['openai', 'gemini', 'qwen'])
def test_missing_api_key(scene, provider):
    factory = fake_factory()
    result = query_scene(scene, 'describe', provider, options=QueryOptions(enable_external_api_calls=True),
                         environ={'QWEN_BASE_URL': 'https://example.invalid/v1'}, client_factory=factory)
    assert result.error_type == 'MISSING_API_KEY'
    assert not result.success
    factory.assert_not_called()


def test_jpeg_roundtrip_no_mutation(scene):
    original = scene.frame.rgb.copy()
    prepared = prepare_image(scene.frame.rgb, 90)
    payload = base64.b64decode(prepared.data_uri().split(',', 1)[1], validate=True)
    assert payload == prepared.jpeg and payload[:2] == b'\xff\xd8'
    decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (480, 640, 3)
    assert prepared.width == 640 and prepared.height == 480
    assert decoded[100, 100, 2] > 250 and decoded[100, 500, 0] > 250
    assert np.array_equal(original, scene.frame.rgb)
    assert not scene.frame.rgb.flags.writeable


@pytest.mark.parametrize('quality', [0, 101, 1.5])
def test_invalid_jpeg_quality(scene, quality):
    with pytest.raises(ValueError):
        prepare_image(scene.frame.rgb, quality)


@pytest.mark.parametrize('provider', ['openai', 'gemini', 'qwen'])
def test_disabled_no_sdk_no_client_no_data_uri(scene, provider, monkeypatch):
    factory = fake_factory()
    def forbidden(*args, **kwargs):
        pytest.fail('Disabled requests must not construct clients or data URIs')
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=forbidden))
    monkeypatch.setattr(PreparedImage, 'data_uri', forbidden)
    env = {'QWEN_BASE_URL': 'https://example.invalid/v1'}
    result = query_scene(scene, 'describe', provider, environ=env)
    assert result.error_type == 'EXTERNAL_API_DISABLED'
    result = query_scene(scene, 'describe', provider, environ=env, client_factory=factory)
    factory.assert_not_called()
    assert result.metadata['scene_id'] == scene.scene_id
    assert result.metadata['width'] == 640 and result.metadata['height'] == 480
    assert len(result.metadata['image_rgb_sha256']) == 64
    assert result.metadata['prompt_version'] == PROMPT_VERSION
    assert result.metadata['status'] == 'EXTERNAL_API_DISABLED'
    assert result.input_tokens is None
    json.dumps(result.metadata)


def test_common_prompt_and_payload(scene):
    requests = []
    for provider in ('openai', 'gemini', 'qwen'):
        factory = fake_factory()
        env = {'OPENAI_API_KEY': 'unit-test-only', 'DASHSCOPE_API_KEY': 'unit-test-only', 'GEMINI_API_KEY': 'unit-test-only',
               'QWEN_BASE_URL': 'https://example.invalid/v1'}
        result = query_scene(scene, 'describe', provider, environ=env, client_factory=factory,
                             options=QueryOptions(enable_external_api_calls=True))
        assert result.success
        kwargs = factory.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
        requests.append(kwargs)
        assert factory.call_args.kwargs['max_retries'] == 0
        assert 'unit-test-only' not in json.dumps(result.metadata)
        assert kwargs['messages'][0]['content'][0]['text'] == SCENE_DESCRIPTION_PROMPT
    assert requests[0]['messages'] == requests[1]['messages'] == requests[2]['messages']
    assert {r['max_tokens'] for r in requests} == {256}
    assert select_prompt('')[0] == select_prompt('describe')[0]
    for forbidden in ('living room', 'Bedroom', 'kitchen', 'master bedroom'):
        assert forbidden not in SCENE_DESCRIPTION_PROMPT


@pytest.mark.parametrize('usage', [None, {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
                                  {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}])
@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_usage_normalization(provider, scene, usage):
    result = query_scene(scene, 'describe', provider, environ={'OPENAI_API_KEY': 'unit-test-only', 'GEMINI_API_KEY': 'unit-test-only'},
                         client_factory=fake_factory(usage), options=QueryOptions(enable_external_api_calls=True))
    assert result.success and result.answer == 'A red cube.'
    assert result.raw_usage == (usage or {})
    assert result.input_tokens == (usage['prompt_tokens'] if usage else None)
    assert result.output_tokens == (usage['completion_tokens'] if usage else None)
    assert result.total_tokens == (usage['total_tokens'] if usage else None)
    assert result.latency_sec >= 0


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_sdk_usage_object(provider, scene):
    usage = SimpleNamespace(model_dump=lambda: {'prompt_tokens': 2, 'completion_tokens': 3,
                            'total_tokens': 5, 'prompt_tokens_details': {'cached_tokens': 1}})
    result = query_scene(scene, 'describe', provider, environ={'OPENAI_API_KEY': 'unit-test-only', 'GEMINI_API_KEY': 'unit-test-only'},
                         client_factory=fake_factory(usage), options=QueryOptions(enable_external_api_calls=True))
    assert result.raw_usage['prompt_tokens_details']['cached_tokens'] == 1
    assert result.total_tokens == 5


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_error_redaction(provider, scene):
    factory = fake_factory()
    factory.side_effect = RuntimeError('Authorization: secret-must-not-escape')
    result = query_scene(scene, 'describe', provider, environ={'OPENAI_API_KEY': 'unit-test-only', 'GEMINI_API_KEY': 'unit-test-only'},
                         client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert result.error_type == 'PROVIDER_ERROR'
    assert 'secret-must-not-escape' not in str(result)


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_empty_response(provider, scene):
    result = query_scene(scene, 'describe', provider, environ={'OPENAI_API_KEY': 'unit-test-only', 'GEMINI_API_KEY': 'unit-test-only'},
                         client_factory=fake_factory(content=None), options=QueryOptions(enable_external_api_calls=True))
    assert result.error_type == 'INVALID_RESPONSE'


@pytest.mark.parametrize('mode,error', [('vqa', 'INVALID_REQUEST'), ('other', 'INVALID_REQUEST')])
def test_deferred_and_invalid_mode(scene, mode, error):
    factory = fake_factory()
    result = query_scene(scene, mode, 'openai', client_factory=factory, environ={})
    assert result.error_type == error
    factory.assert_not_called()


def test_scene_lookup_is_reused(scene):
    buffer = CameraBuffer()
    buffer.update(scene.frame.rgb, 10, 20, 'camera_link')
    captured = buffer.capture()
    result = query_scene(buffer.resolve(captured.scene_id), 'describe', 'openai', environ={})
    assert result.metadata['scene_id'] == captured.scene_id
    assert buffer.resolve(captured.scene_id) is captured

@pytest.mark.parametrize('status,category', [(401, 'AUTHENTICATION_ERROR'), (403, 'ACCESS_DENIED'),
                                           (404, 'NOT_FOUND'), (429, 'RATE_OR_QUOTA_LIMIT'),
                                           (500, 'HTTP_ERROR')])
def test_qwen_safe_http_errors(scene, status, category, monkeypatch):
    monkeypatch.setattr('go2_vlm_scene.providers.base.time.sleep', lambda delay: None)
    import httpx
    import openai
    key = 'sk-test-secret-do-not-log'
    request_id = '12345678-1234-1234-1234-123456789abc'
    response = httpx.Response(status, request=httpx.Request('POST', 'https://example.invalid'),
                              headers={'x-request-id': request_id, 'Authorization': key})
    error = openai.APIStatusError('Authorization: ' + key, response=response,
                                 body={'error': {'code': 'InvalidApiKey', 'message': key},
                                       'request_payload': {'api_key': key}})
    factory = fake_factory()
    factory.return_value.__enter__.return_value.chat.completions.create.side_effect = error
    result = query_scene(scene, 'describe', 'qwen',
                         environ={'DASHSCOPE_API_KEY': key, 'QWEN_BASE_URL': 'https://example.invalid/v1'},
                         client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    diagnostics = json.loads(result.error_message)
    assert diagnostics['http_status'] == status
    assert diagnostics['category'] == category
    assert diagnostics['alibaba_error_code'] == 'InvalidApiKey'
    assert diagnostics['request_id'] == request_id
    assert diagnostics['exception_class'] == 'APIStatusError'
    assert key not in str(result)
    assert 'Authorization' not in str(result)
    assert 'request_payload' not in str(result)
    assert result.metadata['error_message'] == result.error_message
    assert factory.return_value.__enter__.return_value.chat.completions.create.call_count == (3 if status in (429, 500) else 1)
    assert factory.call_args.kwargs['max_retries'] == 0


def test_qwen_untrusted_fields_fail_closed():
    from go2_vlm_scene.providers.qwen_provider import safe_diagnostics
    secret = 'abcdef1234567890abcdef1234567890'
    exc = RuntimeError('Bearer ' + secret)
    exc.body = {'code': secret, 'message': 'Authorization: ' + secret, 'request_id': secret}
    result = safe_diagnostics(exc, {'DASHSCOPE_API_KEY': secret})
    assert result['request_id'] is None
    assert result['alibaba_error_code'] is None
    assert secret not in json.dumps(result)
    exc.body = {'error': {'code': 'unknown-secret-code', 'request_id': 'Bearer secret'}}
    assert safe_diagnostics(exc, {})['request_id'] is None
    assert safe_diagnostics(exc, {})['alibaba_error_code'] is None


@pytest.mark.parametrize('kind,expected', [('dns', 'DNS_ERROR'), ('tls', 'TLS_ERROR'),
                                         ('connection', 'CONNECTION_ERROR'), ('timeout', 'TIMEOUT')])
def test_qwen_transport_classification(kind, expected):
    import ssl
    import httpx
    import openai
    from go2_vlm_scene.providers.qwen_provider import safe_diagnostics
    req = httpx.Request('POST', 'https://example.invalid')
    exc = openai.APITimeoutError(request=req) if kind == 'timeout' else openai.APIConnectionError(request=req)
    if kind == 'dns':
        exc.__cause__ = socket.gaierror('sensitive DNS text')
    elif kind == 'tls':
        exc.__cause__ = ssl.SSLError('sensitive TLS text')
    result = safe_diagnostics(exc, {})
    assert result['category'] == expected
    assert 'sensitive' not in json.dumps(result)
    assert result['http_status'] is None


def test_qwen_correct_sdk_arguments(scene):
    factory = fake_factory()
    env = {'DASHSCOPE_API_KEY': 'test-only', 'QWEN_BASE_URL': 'https://example.invalid/compatible-mode/v1'}
    result = query_scene(scene, 'describe', 'qwen', environ=env, client_factory=factory,
                         options=QueryOptions(enable_external_api_calls=True))
    assert result.success
    assert factory.call_args.kwargs['api_key'] == env['DASHSCOPE_API_KEY']
    assert factory.call_args.kwargs['base_url'] == env['QWEN_BASE_URL']
    call = factory.return_value.__enter__.return_value.chat.completions.create
    call.assert_called_once()
    assert call.call_args.kwargs['model'] == 'qwen3-vl-flash'


def test_gemini_configuration_and_request(scene):
    from go2_vlm_scene.providers.gemini_provider import GeminiProvider
    factory = fake_factory()
    provider = create_provider('gemini', environ={}, client_factory=factory)
    assert isinstance(provider, GeminiProvider)
    assert provider.config.key_env == 'GEMINI_API_KEY'
    assert provider.config.model == 'gemini-3.8-flash'
    assert provider.config.base_url == 'https://generativelanguage.googleapis.com/v1beta/openai/'
    result = query_scene(scene, 'describe', 'gemini', environ={}, client_factory=factory,
                         options=QueryOptions(enable_external_api_calls=True))
    assert result.error_type == 'MISSING_API_KEY'
    assert 'GEMINI_API_KEY' in result.error_message
    factory.assert_not_called()
    result = query_scene(scene, 'describe', 'gemini', environ={'GEMINI_API_KEY': 'test-only'},
                         client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert result.success and result.provider == 'gemini' and result.model == 'gemini-3.8-flash'
    assert factory.call_args.kwargs['base_url'] == provider.config.base_url
    assert factory.call_args.kwargs['api_key'] == 'test-only'
    call = factory.return_value.__enter__.return_value.chat.completions.create
    call.assert_called_once()
    assert call.call_args.kwargs['model'] == provider.config.model


def test_gemini_installed_sdk_offline(scene):
    import httpx
    import openai
    requests = []
    def respond(request):
        requests.append(request)
        assert str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'gemini-3.8-flash'
        assert body['messages'][0]['content'][0]['text'] == SCENE_DESCRIPTION_PROMPT
        payload = body['messages'][0]['content'][1]['image_url']['url']
        assert base64.b64decode(payload.split(',', 1)[1]) == prepare_image(scene.frame.rgb, 90).jpeg
        return httpx.Response(200, json={'id': 'offline', 'object': 'chat.completion',
            'created': 0, 'model': 'gemini-3.8-flash',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': ' A red cube. '},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}})
    def factory(**kwargs):
        return openai.OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    result = query_scene(scene, 'describe', 'gemini', environ={'GEMINI_API_KEY': 'offline-only'},
                         client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert len(requests) == 1
    assert result.success and result.answer == 'A red cube.'
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (10, 5, 15)
    assert 'offline-only' not in str(result)


@pytest.mark.parametrize('status,count', [(408, 3), (429, 3), (500, 3), (502, 3),
    (503, 3), (504, 3), (400, 1), (401, 1), (403, 1), (404, 1), (409, 1), (501, 1)])
def test_bounded_http_retries(scene, monkeypatch, caplog, status, count):
    import httpx
    import openai
    from go2_vlm_scene.providers import base
    # ROS logging setup can disable pre-existing Python loggers during collection.
    monkeypatch.setattr(base.LOGGER, 'disabled', False)
    monkeypatch.setattr(base.LOGGER, 'propagate', True)
    clock = [0.0]
    sleeps = []
    def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
    monkeypatch.setattr(base.time, 'sleep', sleep)
    monkeypatch.setattr(base.time, 'monotonic', lambda: clock[0])
    factory = fake_factory()
    error = openai.APIStatusError('Authorization: secret-test-only',
        response=httpx.Response(status, request=httpx.Request('POST', 'https://example.invalid')),
        body={'message': 'secret-test-only'})
    def fail(**kwargs):
        clock[0] += 0.25
        raise error
    call = factory.return_value.__enter__.return_value.chat.completions.create
    call.side_effect = fail
    with caplog.at_level('INFO', logger=base.__name__):
        result = query_scene(scene, 'describe', 'gemini', environ={'GEMINI_API_KEY': 'secret-test-only'},
            client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert not result.success and call.call_count == count
    assert sleeps == ([2, 4] if count == 3 else [])
    attempts = result.metadata['attempts']
    assert [a['attempt'] for a in attempts] == list(range(1, count + 1))
    assert all(a['http_status'] == status and a['latency_sec'] == 0.25 for a in attempts)
    assert result.latency_sec == count * 0.25 + sum(sleeps)
    assert 'secret-test-only' not in str(result) + caplog.text
    assert 'Authorization' not in caplog.text
    assert 'total_elapsed_sec' in caplog.text
    assert factory.call_args.kwargs['max_retries'] == 0


def test_retry_later_success_identical_payload(scene, monkeypatch):
    import httpx
    import openai
    from go2_vlm_scene.providers import base
    sleeps = []
    monkeypatch.setattr(base.time, 'sleep', sleeps.append)
    factory = fake_factory({'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 5})
    call = factory.return_value.__enter__.return_value.chat.completions.create
    success = call.return_value
    error = openai.APIStatusError('withheld', response=httpx.Response(503,
        request=httpx.Request('POST', 'https://example.invalid')), body={})
    call.side_effect = [error, success]
    result = query_scene(scene, 'describe', 'gemini', environ={'GEMINI_API_KEY': 'test-only'},
        client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert result.success and result.answer == 'A red cube.' and result.total_tokens == 5
    assert call.call_count == 2 and sleeps == [2]
    assert call.call_args_list[0] == call.call_args_list[1]
    assert [a['category'] for a in result.metadata['attempts']] == ['TRANSIENT_HTTP_ERROR', 'SUCCESS']


@pytest.mark.parametrize('kind,count', [('timeout', 3), ('connection', 3), ('tls', 1),
                                      ('dns_permanent', 1), ('configuration', 1)])
def test_transport_retry_classification(scene, monkeypatch, kind, count):
    import httpx
    import openai
    import ssl
    from go2_vlm_scene.providers import base
    sleeps = []
    monkeypatch.setattr(base.time, 'sleep', sleeps.append)
    req = httpx.Request('POST', 'https://example.invalid')
    error = (openai.APITimeoutError(request=req) if kind == 'timeout'
             else openai.APIConnectionError(request=req))
    if kind == 'tls':
        error.__cause__ = ssl.SSLCertVerificationError('secret')
    elif kind == 'dns_permanent':
        error.__cause__ = socket.gaierror(socket.EAI_NONAME, 'secret')
    elif kind == 'configuration':
        error = ValueError('secret')
    factory = fake_factory()
    call = factory.return_value.__enter__.return_value.chat.completions.create
    call.side_effect = error
    result = query_scene(scene, 'describe', 'gemini', environ={'GEMINI_API_KEY': 'test-only'},
        client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert not result.success and call.call_count == count
    assert sleeps == ([2, 4] if count == 3 else [])


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_vqa_shared_prompt_and_image(scene, provider):
    from go2_vlm_scene.prompts import VQA_PROMPT_VERSION, VISUAL_VQA_PROMPT
    factory = fake_factory(content='The cube is green.')
    result = query_scene(scene, 'vqa', provider, question='What colour is the cube?',
        environ={'OPENAI_API_KEY': 'test-only', 'GEMINI_API_KEY': 'test-only'},
        client_factory=factory, options=QueryOptions(enable_external_api_calls=True))
    assert result.success and result.answer == 'The cube is green.'
    assert result.metadata['prompt_version'] == VQA_PROMPT_VERSION == 'visual-vqa-v1'
    assert result.metadata['question'] == 'What colour is the cube?'
    payload = factory.return_value.__enter__.return_value.chat.completions.create.call_args.kwargs
    content = payload['messages'][0]['content']
    assert VISUAL_VQA_PROMPT in content[0]['text']
    assert 'What colour is the cube?' in content[0]['text']
    assert content[1]['image_url']['url'] == prepare_image(scene.frame.rgb, 90).data_uri()
    assert result.answer != str(result.metadata)
    assert 'provider' not in result.answer and scene.scene_id not in result.answer


def test_vqa_instructions_identical():
    from go2_vlm_scene.prompts import select_prompt
    prompt, version = select_prompt('vqa', 'What is visible?')
    assert 'cannot determine' in prompt
    assert 'only' in prompt and 'visible' in prompt
    assert version == 'visual-vqa-v1'
    for question in ('', '   '):
        with pytest.raises(ValueError, match='INVALID_REQUEST'):
            select_prompt('vqa', question)
