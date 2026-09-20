# Task 3: scene description and visual question answering

Task 3 subscribes to `/rgb_image`, retains camera images, and provides scene descriptions and visual question answering (VQA) through `/go2_vlm/query`. It supports OpenAI GPT-4o-mini and Gemini 3.8 Flash. External API calls are **disabled by default**. Task 3 does not publish `/cmd_vel` or decide robot motion.

```text
/rgb_image
     ↓
scene_server
     ↓
retained scene / scene_id
     ↓
provider abstraction
     ├── GPT-4o-mini (openai / gpt-4o-mini)
     └── Gemini 3.8 Flash (gemini / gemini-3.8-flash)
     ↓
describe / VQA
     ↓
/go2_vlm/query (response to the caller)
```

The caller initiates `/go2_vlm/query`; this diagram shows image processing and the returned interpretation. `camera.py` buffers RGB8 frames; `scene_server.py` exposes ROS services; `query_pipeline.py` prepares the retained image and shared prompts; ROS-independent provider adapters perform explicitly enabled inference. Each query sends the selected image; provider conversation history is not required. Qwen remains in legacy adapter code for compatibility and tests, but the ROS query service accepts only `openai` and `gemini`.

## Build and normal launch

The normal runtime does **not** need the formal evaluation dataset. Prerequisites are Ubuntu/ROS 2 Jazzy, colcon, the team Go2 simulation dependencies, and the dependencies declared by both Task 3 packages (including cv_bridge, NumPy, OpenCV, PyYAML, rclpy and pytest). The Python `openai` SDK and its `httpx` dependency must be available to the ROS Python interpreter for enabled operation and the complete mock-provider test suite. Gemini uses that same SDK's OpenAI-compatible endpoint; no Google SDK is needed. Dependency installation is a separate environment setup step, not part of offline regression.

From a clean terminal, change to your clone of `vlm_go2_control`. The commands
below assume the repository root as the working directory:

```bash
cd /path/to/vlm_go2_control
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
export ROS_DOMAIN_ID=42
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
```

Source `/opt/ros/jazzy/setup.bash` and `install/setup.bash` from the repository root, and use the same domain/discovery settings in every ROS terminal. Run from the workspace root so default runtime paths resolve consistently.

Terminal 1 — team simulation (for a separately authorized runtime session):

```bash
ros2 launch go2_house_world apartment_go2.launch.py
```

Use the team root README for simulation dependencies and options. This launch
already bridges `/rgb_image`; do not launch a second simulation. The shared apartment package now supplies the project world and preserved
target placements. Benchmark results still describe the original frozen run.

The repository wrappers resolve their location without a fixed home directory.
They default to this repository as the workspace; `GO2_WORKSPACE` can select
another existing workspace with its own `install/local_setup.bash`. They source
ROS Jazzy, use domain 42 with localhost discovery, create local runtime directories,
and set no Gazebo partition. Any Gazebo environment required by the team must be
set explicitly inside the wrapped command, or use a directly sourced terminal.

Terminal 2 — start exactly one Task 3 server, API-disabled:

```bash
cd /path/to/vlm_go2_control
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch go2_vlm_scene scene.launch.py
```

Terminal 3 — verify the topic/interface and make a disabled query:

```bash
cd /path/to/vlm_go2_control
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic info /rgb_image
ros2 interface show go2_vlm_interfaces/srv/QueryScene
ros2 service call /go2_vlm/query go2_vlm_interfaces/srv/QueryScene \
  '{mode: describe, question: "", provider: openai, scene_id: "", refresh_frame: true}'
```

With a valid camera frame, the disabled call returns `success=false`, an `EXTERNAL_API_DISABLED` error, scene/provider/model metadata, and empty answer/usage. This is the expected safe preflight result. `NO_FRAME` means no valid frame has arrived; `STALE_FRAME` means the live camera receipt age exceeded the configured threshold. Neither requires a cloud request.

## Teammate credentials and explicitly enabled operation

**Every developer supplies their own credentials. Never commit actual keys.** Create the file outside the repository:

```bash
mkdir -p ~/.config/go2_vlm
chmod 700 ~/.config/go2_vlm
nano ~/.config/go2_vlm/credentials.env
chmod 600 ~/.config/go2_vlm/credentials.env
```

Contents (replace placeholders only in that local file):

```bash
export OPENAI_API_KEY='...'
export GEMINI_API_KEY='...'
```

[.env.example](.env.example) contains variable names and placeholders only. Never paste keys into ROS parameters, command arguments, Git, screenshots, or logs. Do not enable shell tracing when loading credentials. The existing `scripts/jazzy_vlm_exec.bash` checks the credential file's ownership and restrictive permissions before loading it; local file assignments override exported shell keys. Loading credentials alone does not enable cloud calls.

For an explicitly authorized live session from the team repository, stop the disabled server first:

```bash
cd /path/to/vlm_go2_control
./scripts/jazzy_vlm_exec.bash ros2 run go2_vlm_scene scene_server --ros-args \
  --params-file src/go2_vlm_scene/config/scene.yaml -p enable_external_api_calls:=true
```

Portable direct equivalent, after sourcing ROS/workspace and setting the domain as above, with your own trusted mode-600 credential file:

```bash
cd /path/to/vlm_go2_control
set +x +v
source ~/.config/go2_vlm/credentials.env
ros2 run go2_vlm_scene scene_server --ros-args \
  --params-file src/go2_vlm_scene/config/scene.yaml -p enable_external_api_calls:=true
```

These enabled commands are documentation only; they were not executed during handoff. Keep `config/scene.yaml` committed with `enable_external_api_calls: false`. Stop the enabled server and relaunch normally to return to disabled operation.

## Task 2 service contract

Service: `/go2_vlm/query`, type [`go2_vlm_interfaces/srv/QueryScene`](../go2_vlm_interfaces/srv/QueryScene.srv).

| Request field | Type | Meaning |
|---|---|---|
| `mode` | `string` | `describe` or `vqa`; empty means `describe`. |
| `question` | `string` | Natural-language question; must be nonempty after trimming for VQA. Ignored by describe. |
| `provider` | `string` | `openai` or `gemini`; empty uses startup `default_provider` (openai). |
| `scene_id` | `string` | Retained UUID for same-image use when refresh is false. Empty selects the latest frame. |
| `refresh_frame` | `bool` | True captures the latest valid frame and overrides scene_id; false resolves a nonempty ID, or captures latest if empty. |

| Response field | Type | Meaning |
|---|---|---|
| `success` | `bool` | Whether the query completed successfully; check before using answer. |
| `answer` | `string` | Description or VQA answer; no structured object pose or motion command. |
| `scene_id` | `string` | Selected retained image UUID; save for conversational follow-up. May be empty if image selection failed. |
| `image_stamp` | `builtin_interfaces/Time` | Original image header time (`sec`, `nanosec`), not query time; may use simulation clock. |
| `frame_id` | `string` | Original camera image frame; does not itself provide a transform or pose. |
| `provider` | `string` | Selected provider identifier. |
| `model` | `string` | Configured model identifier. |
| `latency_sec` | `float64` | Service processing elapsed time, including provider retries/waits; measured before the final audit append. |
| `usage_json` | `string` | JSON object of returned numeric provider usage, or empty if unavailable; provider accounting differs. |
| `error_message` | `string` | Empty on success; sanitized status-prefixed error on failure. No separate status field exists. |

Fresh descriptions (run only the provider call you intend; enabled servers make cloud requests):

```bash
ros2 service call /go2_vlm/query go2_vlm_interfaces/srv/QueryScene \
  '{mode: describe, question: "", provider: openai, scene_id: "", refresh_frame: true}'
ros2 service call /go2_vlm/query go2_vlm_interfaces/srv/QueryScene \
  '{mode: describe, question: "", provider: gemini, scene_id: "", refresh_frame: true}'
```

Follow-up VQA on the same image, using the ID from the intended previous response:

```bash
SCENE_ID='<previous returned scene_id>'
ros2 service call /go2_vlm/query go2_vlm_interfaces/srv/QueryScene \
  "{mode: vqa, provider: openai, question: 'What colour is the cube?', scene_id: '$SCENE_ID', refresh_frame: false}"
ros2 service call /go2_vlm/query go2_vlm_interfaces/srv/QueryScene \
  "{mode: vqa, provider: gemini, question: 'Which objects are visible?', scene_id: '$SCENE_ID', refresh_frame: false}"
```

Task 2 should retain the returned `scene_id` if conversational follow-up is required, send it with `refresh_frame=false`, and display `Robot: <answer>` only when `success=true`. Providers can be switched while retaining the same image. Empty IDs do not mean “previous image”: they capture latest. Unknown/evicted IDs return `SCENE_NOT_FOUND` without silently choosing another frame. On failure, handle `error_message` separately and ask for a fresh description if the retained scene has expired. Do not build unbounded retries around the service.

## Retention, configuration and failure behavior

`config/scene.yaml` contains startup-only configuration. Default `/rgb_image` QoS is best effort, volatile, keep-last depth 5. cv_bridge converts incoming images to RGB8 without hard-coded dimensions. Invalid frames leave the last valid frame intact. Live-frame freshness uses monotonic receipt age (default 2 seconds; 0 disables rejection). Capture freezes the latest received valid frame; it does not wait for a frame newer than the request.

Retained captures are immutable and exempt from live-frame staleness. Default retention is 10 captures, oldest first; lookup does not extend lifetime. IDs disappear on server restart and saved images are not reloaded automatically. `/go2_vlm/capture_scene` (`CaptureScene.srv`) and `ros2 run go2_vlm_scene capture_scene` provide optional capture/saving without inference.

Runtime images and sanitized `queries.jsonl` default to `.runtime/go2_vlm_scene` relative to the working directory; no dataset is needed. Override the launch argument `runtime_data_directory:=/writable/path` or `config:=/path/to/scene.yaml`. Saving never overwrites existing image files and has no automatic deletion. Query audit files use mode 0600; failure to append produces `QUERY_LOG_ERROR` and clears the answer.

Shared provider defaults are JPEG quality 90 at native resolution, maximum output 256 tokens, and 30-second timeout per attempt. The server's image-save JPEG quality is a separate setting. Both active adapters share the non-streaming request builder and bounded transient retry policy: at most three attempts, with 2- then 4-second waits. Retryable HTTP statuses are 408, 429, 500, 502, 503 and 504; timeouts and temporary connection failures also qualify. SDK retries are disabled. Other configuration/HTTP failures, TLS failures and permanent DNS failures stop immediately. The exact prepared image/message payload is reused across attempts. These per-attempt timeouts are not a strict whole-service deadline; allow for preprocessing, waits and audit work.

The shared prompts are `scene-description-v1` and `visual-vqa-v1`. Ground truth is never sent to providers. Errors and audit metadata are sanitized; raw exceptions/headers and credentials are not logged. Numeric usage, attempt timings and image hashes are diagnostic metadata, not natural-language answer content. Prompt instructions do not guarantee factual accuracy.

## Task 4 integration boundary

Task 3 provides **visual interpretation only**. It must not navigate, publish `/cmd_vel`, approach objects, or decide robot motion. Task 4 integration is not implemented here.

Task 4 may later consume `success`/`error_message` to gate interpretation, `answer` as unstructured evidence for grounding/object selection, and `scene_id`, `image_stamp`, `frame_id` to identify the source image. `provider`, `model`, `latency_sec`, and `usage_json` are provenance/diagnostic fields. These outputs contain no bounding boxes, masks, depth, target IDs, confidence calibration, world coordinates, or motion plan. Task 4 owns any additional grounding, transforms, validation, selection and motion logic. A retained image may be old even when a follow-up succeeds.

## Evaluation paths and historical evidence

Evaluation defaults to `.runtime/go2_vlm_scene/evaluation` beneath
`GO2_WORKSPACE`, or the current working directory when unset. Run from the
repository root, or set `GO2_WORKSPACE` explicitly before starting Python.
`--dataset` can select another location within that workspace; the existing
workspace containment checks remain in force. No historical dataset is included.

The published benchmark was performed in the original frozen
`/home/briansyc/go2_jazzy_ws` environment using its apartment world. Its results
are historical evidence, not validation of this team simulation or a new run.

## Offline regression and handoff

Run the complete existing Task 3 suite after building the interfaces; no formal dataset or real credentials are required:

```bash
cd /path/to/vlm_go2_control
source /opt/ros/jazzy/setup.bash
source install/setup.bash
unset OPENAI_API_KEY GEMINI_API_KEY DASHSCOPE_API_KEY QWEN_BASE_URL
export ROS_DOMAIN_ID=43 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/python3 -m pytest -q src/go2_vlm_scene/test
```

The autouse `test/conftest.py` fixture blocks Python socket connection and DNS calls and fails on attempted network use. Providers use mocks/MockTransport. ROS integration uses local DDS and synthetic test image topics, never `/rgb_image` or `/cmd_vel`. Use an isolated domain to avoid collisions with another server. Credential launcher tests use temporary dummy credentials and assert they never reach captured output.

See [handoff and commit manifest](docs/HANDOFF.md) for structure, Git/local boundaries and final regression evidence. [Final benchmark results](docs/BENCHMARK_RESULTS.md) and [evaluation methodology](docs/EVALUATION_METHOD.md) are separate from normal runtime instructions. Do not rerun paid benchmarks or remove their evidence as part of integration.
