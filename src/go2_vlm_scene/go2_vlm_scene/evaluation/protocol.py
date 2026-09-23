"""Fair frozen-image requests, offline payload validation, and explicit live gate."""
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import socket
import time
import yaml
from types import SimpleNamespace
from unittest.mock import patch
from ..prompts import select_prompt
from ..providers import create_provider
from ..providers.config import resolve_config
from ..query_log import QueryLog
from ..types import QueryOptions
from .dataset import MODELS, validate_dataset, load_yaml, digest, utc_now, dataset_lock
from .scoring import score_response
from .reporting import estimate_cost, write_reports


def provider_order(index):
    return ('openai', 'gemini') if index % 2 else ('gemini', 'openai')


def message_hash(messages):
    return digest(json.dumps(messages, sort_keys=True).encode())


@contextmanager
def network_blocked():
    attempted = []
    def forbidden(*args, **kwargs):
        attempted.append(True)
        raise RuntimeError('Network forbidden during evaluation dry run')
    with ExitStack() as stack:
        for owner, name in [(socket.socket,'connect'),(socket.socket,'connect_ex'),
                            (socket,'create_connection'),(socket,'getaddrinfo')]:
            stack.enter_context(patch.object(owner, name, forbidden))
        yield
    if attempted:
        raise RuntimeError('Dry run attempted network access')


def validate_configs(root):
    aliases = load_yaml(Path(root) / 'aliases.yaml')
    pricing = load_yaml(Path(root) / 'pricing.yaml')
    if not isinstance(aliases.get('colors'), list) or not aliases['colors'] or not isinstance(aliases.get('shapes'), dict):
        raise ValueError('Alias colors/shapes configuration required')
    if not isinstance(aliases.get('aliases'), dict):
        raise ValueError('Explicit alias approval table required')
    for phrase, alias in aliases['aliases'].items():
        if (not isinstance(phrase,str) or not isinstance(alias,dict) or
                type(alias.get('approved')) is not bool or alias.get('color') not in aliases['colors'] or
                alias.get('shape') not in aliases['shapes'].values()):
            raise ValueError('Invalid alias entry')
    for provider, model in MODELS.items():
        config = resolve_config(provider, environ={})
        if config.model != model:
            raise ValueError('Active model differs from formal evaluation protocol')
        if pricing.get('providers', {}).get(provider, {}).get('model') != model:
            raise ValueError('Pricing model configuration mismatch')
    if resolve_config('gemini', environ={}).base_url != 'https://generativelanguage.googleapis.com/v1beta/openai/':
        raise ValueError('Gemini endpoint mismatch')
    return aliases, pricing


def dry_run(root):
    root = Path(root)
    report = {'timestamp': utc_now(), 'valid': False, 'real_api_calls': 0,
        'logical_queries_planned': 20, 'max_provider_attempts': 60,
        'providers': MODELS, 'scenes': [], 'errors': []}
    with network_blocked():
        try:
            aliases, _ = validate_configs(root)
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
            report['errors'].append('Provider/alias/pricing configuration missing or invalid')
            return report
        scenes, errors = validate_dataset(root)
        report['errors'].extend(errors)
        prompt, version = select_prompt('describe')
        assert version == 'scene-description-v1'
        for scene in scenes:
            labels = scene['truth']['expected_visible_targets']
            if any(t['color'] not in aliases['colors'] or t['shape'] not in aliases['shapes'].values() for t in labels):
                report['errors'].append(scene['scene_id'] + ': labels absent from canonical alias vocabulary')
                continue
            requests = []
            @contextmanager
            def fake_factory(**kwargs):
                assert kwargs['max_retries'] == 0
                def create(**body):
                    requests.append(body)
                    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Offline payload validation.'))], usage=None)
                yield SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
            order = provider_order(int(scene['scene_id'][-2:]))
            for provider in order:
                adapter = create_provider(provider, environ={'OPENAI_API_KEY':'dry-run-placeholder', 'GEMINI_API_KEY':'dry-run-placeholder'}, client_factory=fake_factory)
                result = adapter.query(scene['image'], prompt, QueryOptions(enable_external_api_calls=True))
                assert result.success and len(result.metadata['attempts']) == 1
            assert len(requests) == 2
            assert requests[0]['messages'] == requests[1]['messages']
            assert {body['max_tokens'] for body in requests} == {256}
            assert requests[0]['messages'][0]['content'][0]['text'] == prompt
            report['scenes'].append({'scene_id':scene['scene_id'], 'provider_order':list(order),
                'width':scene['image'].width,'height':scene['image'].height,
                'image_png_sha256':scene['png_sha256'], 'image_rgb_sha256':scene['image'].rgb_sha256,
                'image_jpeg_sha256':scene['image'].jpeg_sha256, 'jpeg_quality':90, 'max_output_tokens':256,
                'prompt_version':version,'prompt_sha256':digest(prompt.encode()),
                'message_payload_sha256':message_hash(requests[0]['messages']), 'identical_messages':True})
        report['valid'] = not report['errors'] and len(report['scenes']) == 10
    return report


def run_evaluation(root, *, environ=None, client_factory=None):
    """Called only by explicit CLI --execute. Never called by dry_run."""
    root = Path(root)
    env = os.environ if environ is None else environ
    with dataset_lock(root):
        validation = dry_run(root)
        if not validation['valid']:
            raise ValueError('Dataset/protocol validation failed; no API calls permitted')
        for provider in MODELS:
            if not env.get(resolve_config(provider).key_env, '').strip():
                raise ValueError('Both active provider credentials required; values withheld')
        aliases, pricing = validate_configs(root)
        scenes, errors = validate_dataset(root)
        assert not errors
        # No resume/repeat: an interrupted run requires explicit operator handling.
        results_path = root / 'results/results.jsonl'
        if results_path.exists() and results_path.stat().st_size:
            raise ValueError('Existing results must not be overwritten or automatically resumed')
        with (root / 'results/run_started.lock').open('x') as stream:
            stream.write('One 20-query evaluation run. Do not automatically repeat or resume.\n')
        results_path.touch(exist_ok=True)
        config_snapshots = {name:load_yaml(root/name) for name in ('ground_truth.yaml','scene_plan.yaml','aliases.yaml','pricing.yaml')}
        manifest = {'validation':validation, 'configuration':config_snapshots,
                    'configuration_hashes':{name:digest((root/name).read_bytes()) for name in config_snapshots}}
        (root / 'results/protocol.json').write_text(json.dumps(manifest,indent=2,default=str))
        audit = QueryLog(root / 'results', environ=env)
        audit.path = root / 'results/results.jsonl'
        prompt, version = select_prompt('describe')
        for scene in scenes:
            frozen = scene['image']
            expected_digest = next(s['message_payload_sha256'] for s in validation['scenes'] if s['scene_id']==scene['scene_id'])
            for provider in provider_order(int(scene['scene_id'][-2:])):
                config = resolve_config(provider, environ=env)
                transmissions = []
                def guarded_factory(**kwargs):
                    import httpx
                    import openai
                    assert kwargs['max_retries'] == 0 and kwargs['base_url'] == config.base_url
                    def hook(request):
                        assert len(transmissions) < 3, 'Attempt bound exceeded'
                        body = json.loads(request.content)
                        assert body['model'] == config.model and body['max_tokens'] == 256
                        assert message_hash(body['messages']) == expected_digest
                        transmissions.append(True)
                    return openai.OpenAI(**kwargs, http_client=httpx.Client(
                        follow_redirects=False,event_hooks={'request':[hook]}))
                started = time.monotonic()
                adapter = create_provider(provider, environ=env, client_factory=client_factory or guarded_factory)
                result = adapter.query(frozen, prompt, QueryOptions(enable_external_api_calls=True))
                elapsed = time.monotonic() - started
                attempts = result.metadata.get('attempts', [])
                record = {'timestamp':utc_now(), 'scene_id':scene['scene_id'], 'provider':provider,
                    'model':config.model, 'image_png_sha256':scene['png_sha256'],
                    'image_rgb_sha256':frozen.rgb_sha256,'image_jpeg_sha256':frozen.jpeg_sha256,
                    'width':frozen.width,'height':frozen.height,'jpeg_quality':90,
                    'prompt_version':version,'message_payload_sha256':expected_digest,
                    'response':result.answer,'success':result.success,
                    'status':'SUCCESS' if result.success else result.error_type,
                    'attempt_count':len(attempts),'attempts':attempts,
                    'first_attempt_latency_sec':attempts[0]['latency_sec'] if attempts else None,
                    'total_latency_sec':elapsed,'input_tokens':result.input_tokens,
                    'output_tokens':result.output_tokens,'total_tokens':result.total_tokens,
                    'raw_usage':result.raw_usage,
                    'safe_error':{'type':result.error_type,'message':result.error_message}}
                record['score'] = score_response(result.answer, scene['truth'], aliases, result.success)
                record['cost'] = estimate_cost(record, pricing)
                audit.append(record)
        records = [json.loads(line) for line in audit.path.read_text().splitlines()]
        return write_reports(root, records, validation)
