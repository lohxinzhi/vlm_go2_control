"""Separate token accounting, explicit pricing rules, and transparent aggregates."""
import csv
import json
import math
from pathlib import Path
import statistics
from .dataset import MODELS, load_yaml

METRIC_DEFINITIONS = {
    'scoring_denominator': 'Successful queries with deterministic target scoring only; API failures and target-ambiguous responses excluded and counted separately.',
    'target_detection': 'Exact expected (colour, shape) label matches: TP. Detection rate and recall = TP / expected labels in target-scored scenes.',
    'colour_shape_accuracy': 'Correct attributes / expected labels in target-scored scenes; exact matches first, then unambiguous same-colour or same-shape associations.',
    'misses': 'Expected labels absent from exact predictions (FN); wrong colour/shape counts as a miss, not a correct detection.',
    'hallucinations': 'Predicted coloured-object labels not in human-confirmed visible labels (FP). Unresolved wording is manual review, not automatically FP.',
    'precision': 'TP / (TP + FP); null if denominator is zero.',
    'exact_scene_success': 'All target labels correct, no extra coloured target, and no unsupported claim. Unverified background claims require human review; pending values stay null.',
    'latency': 'All recorded logical queries, including failures; total provider-query elapsed time includes client setup and retries/waits. First-attempt latency excludes waits.',
    'tokens': 'Per-provider sums of returned fields only; missing usage counted. Counts are not assumed comparable; total may differ from input plus output.',
    'cost': 'Configured per-model usage rules and per-million rates only. Unconfigured/unavailable costs are null. Retry estimates cover reported final-response usage only and are partial.',
}


def estimate_cost(record, pricing):
    cfg = pricing.get('providers', {}).get(record['provider'], {})
    result = {'cost_status': 'unconfigured', 'currency': cfg.get('currency'), 'estimated_cost': None}
    rates = [cfg.get('input_price_per_million'), cfg.get('output_price_per_million')]
    if (cfg.get('model') != record['model'] or cfg.get('manually_verified') is not True or
            cfg.get('usage_rule_verified') is not True or not cfg.get('date_checked') or
            not cfg.get('currency') or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in rates)):
        return result
    usage = record.get('raw_usage', {})
    incoming = usage.get(cfg.get('input_usage_field'))
    rule = cfg.get('output_usage_rule')
    outgoing = usage.get('completion_tokens') if rule == 'completion_tokens' else None
    if rule == 'total_minus_input' and type(incoming) is int and type(usage.get('total_tokens')) is int:
        outgoing = usage['total_tokens'] - incoming
    if rule not in ('completion_tokens', 'total_minus_input'):
        return result
    if not record['success'] or any(type(v) is not int or v < 0 for v in (incoming, outgoing)):
        result['cost_status'] = 'usage_unavailable'
        return result
    result.update(cost_status='partial_retry_usage' if record['attempt_count'] > 1 else 'estimated',
        estimated_cost=(incoming*rates[0] + outgoing*rates[1]) / 1_000_000,
        billed_input_tokens=incoming, billed_output_tokens=outgoing, output_usage_rule=rule,
        pricing_date_checked=str(cfg['date_checked']))
    return result


def ratio(a, b):
    return a / b if b else None


def aggregate(records):
    summaries = {}
    for provider, model in MODELS.items():
        rows = [r for r in records if r['provider'] == provider]
        scored = [r['score'] for r in rows if r['score']['target_score_status'] == 'scored']
        expected = sum(s['expected_target_count'] for s in scored)
        tp = sum(s['correct_target_detected'] for s in scored)
        fp = sum(s['hallucinated_coloured_target'] for s in scored)
        latency = [r['total_latency_sec'] for r in rows]
        first = [r['first_attempt_latency_sec'] for r in rows if r.get('first_attempt_latency_sec') is not None]
        costs = [r['cost']['estimated_cost'] for r in rows if r['cost']['estimated_cost'] is not None]
        complete_cost = bool(rows) and all(r['cost']['cost_status'] == 'estimated' for r in rows)
        summaries[provider] = {
            'model': model, 'logical_queries': len(rows),
            'successful_api_calls': sum(r['success'] for r in rows),
            'failed_logical_queries': sum(not r['success'] for r in rows),
            'total_provider_attempts': sum(r['attempt_count'] for r in rows),
            'total_retry_count': sum(max(0, r['attempt_count'] - 1) for r in rows),
            'target_scored_scenes': len(scored), 'expected_targets_in_scored_scenes': expected,
            'manual_review_count': sum(bool(r['score']['manual_review_reasons']) for r in rows),
            'target_detection_count': tp if scored else None, 'target_detection_rate': ratio(tp, expected),
            'colour_accuracy': ratio(sum(s['correct_colour'] for s in scored), expected),
            'shape_accuracy': ratio(sum(s['correct_shape'] for s in scored), expected),
            'misses': sum(s['missed_expected_target'] for s in scored) if scored else None,
            'hallucinated_targets': fp if scored else None,
            'precision': ratio(tp, tp + fp), 'recall': ratio(tp, expected),
            'unsupported_scene_claim_count': sum(r['score']['unsupported_scene_claim'] is True for r in rows),
            'unsupported_scene_claim_pending': sum(r['success'] and r['score']['unsupported_scene_claim'] is None for r in rows),
            'exact_scene_success_count': sum(r['score']['exact_scene_success'] is True for r in rows),
            'exact_scene_judged_count': sum(r['score']['exact_scene_success'] is not None for r in rows),
            'mean_latency_sec': statistics.mean(latency) if latency else None,
            'median_latency_sec': statistics.median(latency) if latency else None,
            'minimum_latency_sec': min(latency) if latency else None,
            'maximum_latency_sec': max(latency) if latency else None,
            'mean_first_attempt_latency_sec': statistics.mean(first) if first else None,
            'mean_total_latency_sec': statistics.mean(latency) if latency else None,
            'reported_token_usage': {field: {'sum': sum(r[field] for r in rows if r.get(field) is not None) if any(r.get(field) is not None for r in rows) else None,
                'queries_with_usage': sum(r.get(field) is not None for r in rows),
                'queries_missing_usage': sum(r.get(field) is None for r in rows)}
                for field in ('input_tokens', 'output_tokens', 'total_tokens')},
            'cost_status': 'estimated' if complete_cost else ('unconfigured' if not rows or all(r['cost']['cost_status']=='unconfigured' for r in rows) else 'incomplete'),
            'currency': next((r['cost'].get('currency') for r in rows), None),
            'mean_estimated_cost_per_logical_query': statistics.mean(costs) if complete_cost else None,
            'total_estimated_cost': sum(costs) if complete_cost else None,
            'known_partial_cost_sum': sum(costs) if costs else None,
            'queries_with_complete_cost': sum(r['cost']['cost_status']=='estimated' for r in rows),
        }
    return summaries


def write_reports(root, records, validation):
    root = Path(root)
    reports = root / 'reports'
    reports.mkdir(exist_ok=True)
    summary = {'run_status': 'not_run' if not records else ('complete' if len(records)==20 else 'partial'),
               'validation': validation, 'metric_definitions': METRIC_DEFINITIONS, 'providers': aggregate(records)}
    (reports / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    columns = ['scene_id','provider','model','image_png_sha256','image_jpeg_sha256','prompt_version',
        'response','success','status','attempt_count','first_attempt_latency_sec','total_latency_sec',
        'input_tokens','output_tokens','total_tokens','raw_usage','safe_error','target_score_status',
        'correct_target_detected','correct_colour','correct_shape','missed_expected_target',
        'hallucinated_coloured_target','unsupported_scene_claim','exact_scene_success','manual_review_reasons',
        'cost_status','currency','estimated_cost']
    with (reports / 'comparison.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            row = {**record, **record['score'], **record['cost']}
            writer.writerow({k: json.dumps(row[k]) if isinstance(row.get(k), (dict,list)) else row.get(k) for k in columns})
    lines = ['# Task 3 formal VLM evaluation', '', f"Run status: **{summary['run_status']}**. Real recorded queries: {len(records)}.", '',
        '## Methodology', '',
        'Ten operator-positioned Go2 RGB camera views: five targets, each clear and difficult. Human-confirmed labels are bound to PNG hashes. Each saved PNG is decoded once and JPEG-encoded at native resolution, quality 90. Both providers receive the identical prepared bytes and scene-description-v1 prompt with max_tokens=256. Odd scenes run OpenAI then Gemini; even scenes reverse the order. No ground truth or room labels enter requests.', '',
        'Providers: openai / gpt-4o-mini; gemini / gemini-3.8-flash. Shared ChatCompletionsProvider; maximum three attempts with 2/4-second transient-error waits. No Qwen queries.', '',
        '## Scene validation', '']
    plan_path = root / 'scene_plan.yaml'
    if plan_path.exists():
        lines += ['Planned views (not ground truth):', '', '| ID | Operator location | Planned target | View |', '|---|---|---|---|']
        for scene_id, plan in load_yaml(plan_path)['scenes'].items():
            target = plan['planned_target']
            lines.append(f"| {scene_id} | {plan['room']} | {target['color']} {target['shape']} | {plan['difficulty']} |")
        lines.append('')
    for scene in validation.get('scenes', []):
        lines.append(f"- {scene['scene_id']}: {scene['width']}×{scene['height']}; JPEG SHA-256 `{scene['image_jpeg_sha256']}`")
    for error in validation.get('errors', []):
        lines.append('- Pending: ' + error)
    lines += ['', '## Factual provider metrics', '', '| Metric | OpenAI | Gemini |', '|---|---|---|']
    for key in summary['providers']['openai']:
        if key == 'model': continue
        values = [summary['providers'][p][key] for p in MODELS]
        lines.append('| '+key+' | '+' | '.join(json.dumps(v, ensure_ascii=False) for v in values)+' |')
    lines += ['', '## Correctness and responses', '']
    for r in records:
        lines += [f"### {r['scene_id']} / {r['provider']}", '', r['response'] or '(No answer)', '',
                  'Score: `' + json.dumps(r['score'], ensure_ascii=False) + '`', '',
                  'Attempts: `' + json.dumps(r.get('attempts', [])) + '`', '']
    lines += ['## Definitions and limitations', '']
    lines += [f'- **{key}**: {value}' for key,value in METRIC_DEFINITIONS.items()]
    lines += ['', 'Ambiguous target language, negation, repeated objects, and unverified background assertions are flagged for manual review. This phrase-based scorer does not establish semantic truth for arbitrary natural language. Manual-review exclusions and denominators are shown explicitly. Ten selected scenes are not evidence of universal superiority. Run order alternation reduces but does not eliminate timing/service-load effects. Timeouts may have incurred unreported provider work/cost. No subjective overall score or winner is assigned.', '']
    (reports / 'evaluation_report.md').write_text('\n'.join(lines))
    return summary
