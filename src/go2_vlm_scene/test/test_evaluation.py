"""Formal-evaluation checks: synthetic fixtures only, never a real provider."""
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import yaml
from go2_vlm_scene.evaluation.dataset import init_dataset, save_capture, validate_dataset, load_yaml
from go2_vlm_scene.evaluation.protocol import dry_run, provider_order
from go2_vlm_scene.evaluation.scoring import score_response
from go2_vlm_scene.evaluation.reporting import estimate_cost, aggregate, write_reports


@pytest.fixture
def dataset(tmp_path):
    root = tmp_path / 'evaluation'
    init_dataset(root)
    truth = load_yaml(root / 'ground_truth.yaml')
    for i, (scene_id, plan) in enumerate(load_yaml(root / 'scene_plan.yaml')['scenes'].items(), 1):
        image = np.zeros((48, 64, 3), np.uint8)
        image[:, :, 1] = i * 20
        source = tmp_path / f'capture_{i}.png'
        assert cv2.imwrite(str(source), image)
        meta = save_capture(root, scene_id, source, {'scene_id': f'capture-{i}',
            'image_stamp': {'sec': i, 'nanosec': 0}, 'frame_id': 'test_camera'})
        truth['scenes'][scene_id].update(room=plan['room'], difficulty=plan['difficulty'],
            expected_visible_targets=[plan['planned_target']], human_confirmed=True,
            confirmed_by='OFFLINE FIXTURE ONLY', confirmed_at='2026-09-20',
            confirmed_image_sha256=meta['png_sha256'])
    (root / 'ground_truth.yaml').write_text(yaml.safe_dump(truth, sort_keys=False))
    return root


def test_dry_run_ten_images_and_provider_order(dataset):
    report = dry_run(dataset)
    assert report['valid'] and report['real_api_calls'] == 0
    assert report['logical_queries_planned'] == 20 and report['max_provider_attempts'] == 60
    assert len(report['scenes']) == 10
    assert provider_order(1) == ('openai', 'gemini')
    assert provider_order(2) == ('gemini', 'openai')
    for scene in report['scenes']:
        assert scene['identical_messages']
        assert scene['prompt_version'] == 'scene-description-v1'
        assert scene['width'] == 64 and scene['height'] == 48
    assert (dataset / 'results/results.jsonl').read_text() == ''


def test_unconfirmed_or_missing_ground_truth_blocks(tmp_path):
    root = tmp_path / 'eval'
    init_dataset(root)
    truth = load_yaml(root / 'ground_truth.yaml')
    assert all(not s['human_confirmed'] and not s['expected_visible_targets'] for s in truth['scenes'].values())
    report = dry_run(root)
    assert not report['valid'] and report['real_api_calls'] == 0
    assert len(report['errors']) >= 10


def test_capture_no_overwrite_and_reconfirmation(dataset, tmp_path):
    source = tmp_path / 'new.png'
    cv2.imwrite(str(source), np.full((48, 64, 3), 200, np.uint8))
    with pytest.raises(FileExistsError):
        save_capture(dataset, 'scene_01', source, {})
    save_capture(dataset, 'scene_01', source, {'scene_id': 'replacement',
        'image_stamp': {'sec': 20, 'nanosec': 0}, 'frame_id': 'camera'}, overwrite=True)
    assert not load_yaml(dataset / 'ground_truth.yaml')['scenes']['scene_01']['human_confirmed']
    assert validate_dataset(dataset)[1]
    with pytest.raises(ValueError):
        save_capture(dataset, '../escape', source, {})


def test_hash_tampering_and_duplicate_images(dataset):
    first = dataset / 'images/scene_01.png'
    second = dataset / 'images/scene_02.png'
    second.write_bytes(first.read_bytes())
    errors = validate_dataset(dataset)[1]
    assert any('hash' in e.lower() or 'Duplicate RGB' in e for e in errors)


def test_truth_never_enters_payload(dataset):
    gt = load_yaml(dataset / 'ground_truth.yaml')
    gt['scenes']['scene_01']['notes'] = 'SECRET_GROUND_TRUTH_MARKER'
    (dataset / 'ground_truth.yaml').write_text(yaml.safe_dump(gt))
    report = dry_run(dataset)
    assert report['valid']
    assert 'SECRET_GROUND_TRUTH_MARKER' not in json.dumps(report)


@pytest.fixture
def aliases(tmp_path):
    init_dataset(tmp_path)
    return load_yaml(tmp_path / 'aliases.yaml')


def gt(color='green', shape='cube'):
    return {'expected_visible_targets': [{'color': color, 'shape': shape}],
            'supported_scene_phrases': [], 'unsupported_scene_phrases': []}


@pytest.mark.parametrize('text', ['A green cube.', 'A green block.', 'A green box.'])
def test_approved_aliases(text, aliases):
    score = score_response(text, gt(), aliases)
    assert score['correct_target_detected'] == 1
    assert score['correct_colour'] == 1 and score['correct_shape'] == 1
    assert score['exact_scene_success'] is True


def test_red_alias_and_unapproved_blue_tube(aliases):
    assert score_response('A red triangular object.', gt('red', 'triangular_prism'), aliases)['correct_target_detected'] == 1
    score = score_response('A blue tube.', gt('blue', 'cylinder'), aliases)
    assert score['target_score_status'] == 'manual_review'
    assert score['correct_target_detected'] is None


def test_negation_uncertainty_counts_manual(aliases):
    for text in ('There is no green cube.', 'Maybe a green cube.', 'Two green cubes.', 'It is green.'):
        score = score_response(text, gt(), aliases)
        assert score['target_score_status'] == 'manual_review'


def test_wrong_colour_miss_and_hallucination(aliases):
    score = score_response('A red cube.', gt(), aliases)
    assert score['correct_target_detected'] == 0
    assert score['correct_colour'] == 0 and score['correct_shape'] == 1
    assert score['missed_expected_target'] == 1 and score['hallucinated_coloured_target'] == 1


def test_unsupported_claim_requires_review(aliases):
    score = score_response('A green cube beside a sofa.', gt(), aliases)
    assert score['correct_target_detected'] == 1
    assert score['unsupported_scene_claim'] is None and score['exact_scene_success'] is None
    truth = gt()
    truth['unsupported_scene_phrases'] = ['sofa']
    assert score_response('A green cube beside a sofa.', truth, aliases)['unsupported_scene_claim'] is True
    truth['unsupported_scene_phrases'] = []
    truth['supported_scene_phrases'] = ['sofa']
    assert score_response('A green cube beside a sofa.', truth, aliases)['unsupported_scene_claim'] is False


def record(provider='openai', success=True):
    return {'scene_id': 'scene_01', 'provider': provider,
        'model': 'gpt-4o-mini' if provider == 'openai' else 'gemini-3.8-flash',
        'success': success, 'response': 'A green cube.' if success else '',
        'attempt_count': 1, 'first_attempt_latency_sec': 1.0, 'total_latency_sec': 2.0,
        'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 125,
        'raw_usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 125}}


def test_unconfigured_cost_and_explicit_usage_rule(tmp_path):
    init_dataset(tmp_path)
    pricing = load_yaml(tmp_path / 'pricing.yaml')
    r = record('gemini')
    assert estimate_cost(r, pricing)['cost_status'] == 'unconfigured'
    # Deliberately artificial prices for arithmetic tests, not production prices.
    cfg = pricing['providers']['gemini']
    cfg.update(manually_verified=True, usage_rule_verified=True, date_checked='2026-09-20',
               input_price_per_million=1.0, output_price_per_million=2.0,
               input_usage_field='prompt_tokens', output_usage_rule='total_minus_input')
    cost = estimate_cost(r, pricing)
    assert cost['estimated_cost'] == pytest.approx(0.00015)
    r['attempt_count'] = 2
    assert estimate_cost(r, pricing)['cost_status'] == 'partial_retry_usage'


def test_aggregate_failure_and_manual_denominators(aliases, tmp_path):
    init_dataset(tmp_path)
    pricing = load_yaml(tmp_path / 'pricing.yaml')
    good = record()
    good['score'] = score_response(good['response'], gt(), aliases)
    good['cost'] = estimate_cost(good, pricing)
    failure = record(success=False)
    failure.update(scene_id='scene_02', attempt_count=3)
    failure['score'] = score_response('', gt(), aliases, success=False)
    failure['cost'] = estimate_cost(failure, pricing)
    summary = aggregate([good, failure])['openai']
    assert summary['successful_api_calls'] == 1 and summary['failed_logical_queries'] == 1
    assert summary['total_retry_count'] == 2 and summary['precision'] == 1
    assert summary['target_scored_scenes'] == 1
    assert summary['total_estimated_cost'] is None
    write_reports(tmp_path, [good, failure], {'valid': False, 'errors': ['incomplete test run']})
    assert (tmp_path / 'reports/comparison.csv').exists()
    assert (tmp_path / 'reports/summary.json').exists()
    assert (tmp_path / 'reports/evaluation_report.md').exists()


def test_full_mock_run_20_records_and_no_replay(dataset, monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    import httpx
    import openai
    from go2_vlm_scene.evaluation.protocol import run_evaluation
    calls, waits = [], []
    monkeypatch.setattr('go2_vlm_scene.providers.base.time.sleep', waits.append)
    @contextmanager
    def fake_factory(**kwargs):
        assert kwargs['max_retries'] == 0
        def create(**body):
            calls.append(body)
            if len(calls) == 1:
                raise openai.APIStatusError('Authorization: secret', response=httpx.Response(503,
                    request=httpx.Request('POST','https://example.invalid')), body={})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='A green cube.'))],
                usage={'prompt_tokens':100,'completion_tokens':4,'total_tokens':104})
        yield SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    summary = run_evaluation(dataset, environ={'OPENAI_API_KEY':'mock-only','GEMINI_API_KEY':'mock-only'}, client_factory=fake_factory)
    assert summary['run_status'] == 'complete' and len(calls) == 21 and waits == [2]
    rows = [json.loads(line) for line in (dataset/'results/results.jsonl').read_text().splitlines()]
    assert len(rows) == 20 and rows[0]['attempt_count'] == 2
    for i in range(10):
        first, second = rows[2*i:2*i+2]
        assert [first['provider'],second['provider']] == list(provider_order(i+1))
        assert first['image_jpeg_sha256'] == second['image_jpeg_sha256']
        assert first['message_payload_sha256'] == second['message_payload_sha256']
    for request in calls:
        text = request['messages'][0]['content'][0]['text']
        assert 'living_room' not in text and 'bedroom' not in text and 'ground_truth' not in text
    with pytest.raises((FileExistsError, ValueError)):
        run_evaluation(dataset, environ={'OPENAI_API_KEY':'mock-only','GEMINI_API_KEY':'mock-only'}, client_factory=fake_factory)
    assert len(calls) == 21


def test_invalid_dataset_execute_stops_before_client(tmp_path):
    from go2_vlm_scene.evaluation.protocol import run_evaluation
    root=tmp_path/'eval'
    init_dataset(root)
    def forbidden(**kwargs):
        pytest.fail('Invalid dataset must not construct a client')
    with pytest.raises(ValueError):
        run_evaluation(root, client_factory=forbidden, environ={})


def test_two_targets_and_extra_target(aliases):
    s = score_response('A green cube and a purple cylinder.', gt(), aliases)
    assert s['correct_target_detected'] == 1 and s['hallucinated_coloured_target'] == 1
    assert s['exact_scene_success'] is False


def test_unverified_and_mismatched_pricing_stays_unconfigured(tmp_path):
    init_dataset(tmp_path)
    pricing=load_yaml(tmp_path/'pricing.yaml')
    pricing['providers']['openai']['input_price_per_million']=1
    pricing['providers']['openai']['output_price_per_million']=2
    assert estimate_cost(record(),pricing)['estimated_cost'] is None
    pricing['providers']['openai'].update(manually_verified=True,usage_rule_verified=True,date_checked='2026-09-20',model='wrong-model')
    assert estimate_cost(record(),pricing)['cost_status']=='unconfigured'


def test_approved_background_does_not_look_like_target(aliases):
    truth = gt()
    truth['supported_scene_phrases'] = ['grey walls']
    score = score_response('A green cube with grey walls.', truth, aliases)
    assert score['correct_target_detected'] == 1 and score['exact_scene_success'] is True


def test_ambiguous_partial_association_needs_review(aliases):
    truth = gt('green', 'cylinder')
    truth['expected_visible_targets'].append({'color':'blue','shape':'cylinder'})
    score = score_response('A red cylinder.', truth, aliases)
    assert score['target_score_status'] == 'manual_review'


def test_plan_cannot_replace_required_target_views(dataset):
    plan = load_yaml(dataset/'scene_plan.yaml')
    plan['scenes']['scene_01']['room'] = 'kitchen'
    (dataset/'scene_plan.yaml').write_text(yaml.safe_dump(plan))
    assert any('required five targets' in e for e in validate_dataset(dataset)[1])
