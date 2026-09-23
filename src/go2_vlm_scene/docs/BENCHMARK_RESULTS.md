# Task 3 final benchmark results

> Historical benchmark documentation: the benchmark was performed in the original
> frozen `/home/briansyc/go2_jazzy_ws` environment and apartment world. Paths and
> commands below refer to that environment; they are not team setup instructions.
> No benchmark was rerun during integration. See [README](../README.md) for
> portable runtime and evaluation path configuration.

Completed Stage 4D inference and Stage 4G human reconciliation; handoff performed without any new inference. This document is safe to commit independently of the local dataset. It does not authorize a rerun.

## Methodology

Ten distinct 640×480 saved camera scenes, one human-confirmed coloured target per image, covering five rooms with a clear and a difficult view each. Targets: green cube (01–02), red triangular prism (03–04), blue cylinder (05–06), yellow cube (07–08), purple cylinder (09–10). Both providers received identical native-resolution JPEG quality-90 image bytes and scene-description-v1 instructions, maximum output 256 tokens, without labels or ground truth. Provider order alternated by scene. There were 20 logical description queries; no VQA, navigation or Task 4 benchmark calls.

## API/service reliability and retries

| Metric | GPT-4o-mini | Gemini 3.8 Flash |
|---|---:|---:|
| Logical queries | 10 | 10 |
| Successful / attempted | 10/10 | 9/10 |
| Failures / attempted | 0/10 | 1/10 |
| External requests | 10 | 16 |
| Retries | 0 | 6 |

Gemini scene_06 failed after three HTTP 429 attempts and remains `not_evaluable_api_failure`, never a visual miss. Other Gemini retry observations: scene_04 one HTTP 503 before success; scene_07 one HTTP 429 before success; scene_08 two HTTP 503 responses before success. Shared policy: at most three attempts with 2/4-second retry waits. Across the run, 26 HTTP responses comprised 19 HTTP 200, four HTTP 429 and three HTTP 503.

## Final human visual correctness

All 19 successful responses have complete human judgments; zero unresolved visual annotations. GPT denominator 10, Gemini denominator 9. Human object correspondence separates detecting the real target from misdescribing an attribute; an attribute error is not automatically a miss or extra hallucinated object.

| Metric | GPT-4o-mini | Gemini 3.8 Flash |
|---|---:|---:|
| Target detection | 10/10 (100.00%) | 9/9 (100.00%) |
| Colour accuracy | 9/10 (90.00%) | 9/9 (100.00%) |
| Shape accuracy | 10/10 (100.00%) | 8/9 (88.89%) |
| Exact-scene success | 9/10 (90.00%) | 8/9 (88.89%) |
| Misses | 0/10 (0.00%) | 0/9 (0.00%) |
| Scenes with hallucinated coloured targets | 0/10 (0.00%) | 0/9 (0.00%) |
| Unsupported background claims | 0/10 (0.00%) | 0/9 (0.00%) |

Distinct hallucinated coloured targets: 0 for each provider. GPT scene_08 detected the target but had incorrect colour; Gemini scene_04 detected the target but had incorrect shape. Both have exact-scene success no; all other successful responses have detection, colour, shape and exact success yes. Human answers and reviewer notes were preserved without reinterpretation.

## Latency

Seconds across all 10 logical queries per provider, including failures, setup and retry waits. Image preprocessing precedes the provider timing.

| Statistic | GPT-4o-mini | Gemini 3.8 Flash |
|---|---:|---:|
| mean_latency_sec | 1.7437848427998688 | 9.623518368499935 |
| median_latency_sec | 1.4340774844995394 | 6.989932895000038 |
| minimum_latency_sec | 1.1248338800005513 | 4.3044791479997 |
| maximum_latency_sec | 3.6054447249998702 | 29.224668181999732 |
| mean_first_attempt_latency_sec | 1.7228400711999712 | 6.276378782200117 |
| mean_total_latency_sec | 1.7437848427998688 | 9.623518368499935 |

## Provider-reported usage and cost

| Returned sum | OpenAI | Gemini |
|---|---:|---:|
| Input | 142320 | 10107 |
| Output | 490 | 484 |
| Total | 142810 | 12109 |
| Queries reporting / missing usage | 10 / 0 | 9 / 1 |

OpenAI and Gemini token accounting is provider-specific and not directly comparable. Gemini total is not forced to equal input plus output. Failed-attempt usage is unavailable, so these figures are not complete retry billing totals. Pricing and usage rules have not been independently verified: cost remains unconfigured, with null estimates.

## Limitations and preserved evidence

Small, fixed simulated dataset, one logical query per provider/scene, no repeated-run variance or generalization claim. Gemini visual coverage excludes one scene. Yellow appears darker/olive under the simulated lighting; locked human labels were retained. Human reviewer name/date were not supplied; optional metadata remains blank. Model answers remain fallible. No overall winner, ranking, composite score or recommendation is reported.

Evidence stays local under `.runtime/go2_vlm_scene/evaluation/`: `images/`, `ground_truth.yaml`, `results/results.jsonl`, `results/protocol.json`, `stage4d/`, and `reports/` (completed packet, canonical human CSV, comparison CSV, summary JSON and final report). Do not delete or alter it during merge preparation. Historical deterministic score columns may contain pending flags; final comparison fields are `human_*`, and final summary values are `providers.*.human_visual_metrics`.

Stage 4G verified 19 human-reviewed successes, one non-evaluable failure, zero unconfirmed judgments and zero external calls; raw responses/images/ground truth were unchanged. This Git-safe summary was transcribed from the finalized summary.json; full precision is preserved above.
