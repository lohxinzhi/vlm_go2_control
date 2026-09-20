# Task 3 evaluation methodology reference

> Historical benchmark documentation: the benchmark was performed in the original
> frozen `/home/briansyc/go2_jazzy_ws` environment and apartment world. Paths and
> commands below refer to that environment; they are not team setup instructions.
> No benchmark was rerun during integration. See [README](../README.md) for
> portable runtime and evaluation path configuration.

The formal run and Stage 4G reconciliation are complete. See [final results](BENCHMARK_RESULTS.md). This is the retained methodology for audit, not a normal runtime prerequisite or an instruction to rerun the dataset. Historical deterministic scoring differs from the final human object-correspondence metrics. Do not overwrite or delete the completed local evidence.

## Stage 4: formal ten-scene evaluation (offline setup first)

The evaluation dataset lives at
`/home/briansyc/go2_jazzy_ws/.runtime/go2_vlm_scene/evaluation`, outside install
resources. Task 3 does not move the robot. The operator positions Go2 using the
existing controls, then captures each current `/rgb_image` through Stage 1.
No scene is created from a synthetic render or inferred from a room label.

```bash
./scripts/jazzy_exec.bash colcon build --packages-select go2_vlm_scene
./scripts/jazzy_exec.bash ros2 run go2_vlm_scene evaluate_scenes --init
# Position the robot manually before each capture. No VLM call occurs here.
./scripts/jazzy_exec.bash ros2 run go2_vlm_scene capture_eval_scene --scene-id scene_01
# Repeat for scene_02 ... scene_10 at the required viewpoints.
./scripts/jazzy_exec.bash ros2 run go2_vlm_scene evaluate_scenes --dry-run
```

Capture requires the normal Stage 1 scene server, with PNG saving. The evaluation
utility copies the lossless saved PNG into `images/scene_XX.png` and records its
capture UUID, camera timestamp/frame ID, dimensions, and PNG/RGB SHA-256 in
`images/scene_XX.json`. The stable evaluation ID is separate from the retained
server UUID. Existing scenes are rejected unless `--overwrite` is explicit;
overwriting clears human confirmation and requires a new image review. Capture
never publishes `/cmd_vel`, and never invokes a VLM.

The transparent planning file `scene_plan.yaml` assigns these views:

| Scene IDs | Operator location / target | Views |
|---|---|---|
| scene_01, scene_02 | living room / green cube | clear, difficult |
| scene_03, scene_04 | Bedroom 1 / red triangular prism | clear, difficult |
| scene_05, scene_06 | Bedroom 2 / blue cylinder | clear, difficult |
| scene_07, scene_08 | master bedroom / yellow cube | clear, difficult |
| scene_09, scene_10 | kitchen / purple cylinder | clear, difficult |

For the difficult view, use greater distance, an angle, background clutter, or
less ideal framing while keeping the object identifiable by a human. Do not
fully hide the target. Images must be distinct. Planning labels are never copied
into ground truth and never passed to the models.

### Human ground truth

Open every PNG and edit `ground_truth.yaml` only after inspecting that image.
The generated entries are deliberately unconfirmed with **empty target lists**.
The following is an example of a *human-completed* entry, not an automatic label:

```yaml
version: 1
scenes:
  scene_01:
    image: images/scene_01.png
    room: living_room
    difficulty: clear
    expected_visible_targets:
      - {color: green, shape: cube}
    supported_scene_phrases: [floor]  # Only visible, human-confirmed evidence.
    unsupported_scene_phrases: []   # Explicitly contradicted claims, if known.
    human_confirmed: true
    confirmed_by: '<human evaluator name>'
    confirmed_at: 'YYYY-MM-DD'
    confirmed_image_sha256: '<PNG hash from images/scene_01.json>'
    notes: '<viewpoint/visibility observations>'
```

List **all actually visible coloured targets**, including any incidental ones.
Do not fill a target solely because of the planned room. If the required target
is not identifiable, recapture the scene. The program validates the attestation
and image hash; it cannot authenticate a human's identity or judgement.
Ground truth, alias/pricing settings and image hashes are snapshotted for a run.
Keep them fixed before inference and report any later review separately.

### Fair protocol and dry run

`--dry-run` is the default action. It blocks Python networking, validates all ten
images and human confirmations, and runs the **actual shared request builder**
with mock clients and dummy keys. It never imports a live SDK client. Each PNG is
decoded once to native RGB and encoded at JPEG quality 90; both provider requests
receive the identical prepared image object and `scene-description-v1` prompt,
with `max_tokens=256`. Full message hashes are compared. Ground truth, planning
labels and scene IDs are not included in the provider message.

Odd scenes execute openai/gpt-4o-mini then gemini/gemini-3.8-flash; even scenes
reverse that order. The shared transient retry policy allows three attempts
with 2/4-second waits. SDK retries and redirects are disabled in the live runner.
There are **20 logical queries**, with **at most 60 provider attempts**. No VQA,
Qwen, navigation or Task 4 calls are part of this benchmark.

Missing images, changed hashes, duplicate RGB captures, missing/unconfirmed
labels, or invalid configs produce a nonzero dry-run exit and actionable errors
in `reports/dry_run.json`. A blocked validation is not a completed evaluation.
Synthetic images are used only in temporary offline test fixtures, not in this
dataset. Dry run never creates fake model results.

The optional `--execute` mode exists for a **separately authorized** future paid
run after dry-run validation passes. It is never selected implicitly. It checks
both keys, creates an exclusive run lock, and refuses to overwrite existing
results or automatically resume an interrupted run. Do not delete the lock to
silently repeat paid queries. The scene-server default remains API-disabled;
the offline-image runner enables only its own explicit execution.

### Deterministic scoring and metrics

`aliases.yaml` is the visible approved phrase table. Canonical colour/shape pairs
are recognized along with approved `green block`/`green box` → green cube and
`red triangular object` → red triangular prism aliases. `blue tube` is explicitly
**unapproved** by default; it needs human alias approval before it can count as a
cylinder. No other VLM judges responses.

Exact colour/shape label matches are true positives (TP). Expected labels not
matched exactly are misses (FN); extra predicted coloured-target labels are
false positives (FP). A wrong colour/shape can therefore produce both an FN and
an FP. Colour/shape accuracy also uses unambiguous partial object associations.
Negation, uncertainty, repeated object references, plural counts, unknown labels,
and ambiguous associations are flagged for manual review instead of guessing.
Unverified background assertions are also flagged; explicit human-confirmed
supported/unsupported evidence phrases determine those classifications. Phrase
matching is conservative and does not prove arbitrary natural-language claims.

Target detection rate and recall = TP / expected labels in deterministically
scored successful scenes. Precision = TP / (TP + FP). Colour/shape accuracy uses
the same expected-label denominator. API failures and target-manual-review rows
are excluded from these accuracy denominators and their counts/coverage are
reported separately. Exact-scene success needs every target correct, no extra
target and no unsupported claim; unresolved background claims remain pending.
No subjective overall score or winner is produced.

Mean/median/minimum/maximum logical-query latency include retries and waits and
include failed queries. Mean first-attempt latency is also reported. Shared
image preprocessing happens once per scene before the timed provider queries.
Token fields and raw numeric usage are kept separately for each provider; absent
counts are not zero and reported totals are not forced to equal input + output.

### Pricing and outputs

`pricing.yaml` is separate from provider classes. No prices are supplied.
`cost_status=unconfigured` and null cost values remain until a human verifies the
model, currency, date checked, input/output per-million rates, and provider usage
rules. Supported explicit output rules are `completion_tokens` or
`total_minus_input`; choose only according to verified provider billing rules.
The simple estimator requires those rules to cover the actual billing case
(e.g. any cached/thinking tokens); otherwise leave it unconfigured. Retry costs
may be incomplete because failed attempts may have unreported usage. Such values
are labelled `partial_retry_usage`; aggregate full cost stays null rather than
silently treating unknown cost as zero.

Outputs:
- `results/results.jsonl`: one sanitized record per actual provider/scene logical
  query; empty before the live run. Includes response, hashes, prompt version,
  attempts, latencies, usage, scoring, cost status and safe failure information.
- `results/protocol.json`: immutable-run configuration and fairness snapshot,
  generated only when a real run starts.
- `reports/dry_run.json`: offline validation details.
- `reports/comparison.csv`: one row per recorded provider/scene pair; header-only
  before inference.
- `reports/summary.json`: provider metrics, denominators and run status.
- `reports/evaluation_report.md`: methodology, scene plan, validation status,
  correctness/latency/failure/token/cost observations and limitations.

All JSONL records use the existing credential redactor. Stored response text is
otherwise unchanged; credential/header content is never retained. Failed or
interrupted runs keep their completed records and must not be silently replayed.
