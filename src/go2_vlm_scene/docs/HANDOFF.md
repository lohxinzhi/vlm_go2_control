# Task 3 team handoff and merge preparation

> Historical Stage 5 record from the frozen `/home/briansyc/go2_jazzy_ws`
> environment. Workspace paths, apartment launch instructions, wrapper limitations,
> and test results below describe that original environment, not the integrated
> repository. For current portable build/runtime instructions use [README](../README.md).
> Stage 6A changes only the integration copy; its manifest excludes generated caches.
> The original benchmark evidence has not been transferred or rerun.

Stage 5 prepares documentation and repository hygiene only. Runtime implementation, interfaces, tests, Task 2/Task 4 implementations, robot/world/camera/controller files and formal evaluation evidence are unchanged. No external API calls were made. The only packaging change installs the new Markdown documents alongside the README.

## Package and file structure

```text
src/go2_vlm_interfaces/
├── CMakeLists.txt
├── package.xml
└── srv/
    ├── CaptureScene.srv
    └── QueryScene.srv
src/go2_vlm_scene/
├── .env.example, .gitignore
├── package.xml, setup.py, setup.cfg
├── resource/go2_vlm_scene
├── README.md
├── docs/
│   ├── HANDOFF.md
│   ├── GIT_FILES.txt
│   ├── BENCHMARK_RESULTS.md
│   └── EVALUATION_METHOD.md
├── config/
│   ├── scene.yaml
│   ├── evaluation_aliases.yaml
│   └── evaluation_pricing.yaml
├── launch/scene.launch.py
├── go2_vlm_scene/
│   ├── camera.py, image_storage.py, image_encoding.py
│   ├── scene_server.py, capture_cli.py
│   ├── query_pipeline.py, query_log.py, prompts.py, types.py
│   ├── providers/{base,config,openai_provider,gemini_provider,qwen_provider}.py
│   └── evaluation/{cli,dataset,protocol,reporting,scoring}.py
└── test/
    ├── conftest.py
    ├── test_camera.py
    ├── test_providers.py
    ├── test_credentials_launcher.py
    ├── test_ros_pipeline.py
    ├── test_stage3.py
    └── test_evaluation.py
scripts/jazzy_vlm_exec.bash
scripts/jazzy_exec.bash                # existing shared dependency
.gitignore
```

Python package `__init__.py` files are included in the exact [Git file manifest](GIT_FILES.txt). The legacy Qwen adapter stays to preserve existing tested behavior; it is not an active ROS query provider.

## Intended Git contents

Commit both Task 3 packages: Python source, service definitions, package metadata, resource marker, launch/config files, tests, README and documentation, placeholder `.env.example`, and ignore rules. Include `scripts/jazzy_vlm_exec.bash` and retain the existing shared `scripts/jazzy_exec.bash` dependency if not already in the team repository. Merge the workspace `.gitignore` entries into any existing team rules rather than replacing unrelated rules. `GIT_FILES.txt` lists every intended file; review it before staging.

The safe methodology and final factual benchmark summary are in `docs/EVALUATION_METHOD.md` and `docs/BENCHMARK_RESULTS.md`. They suffice for the handoff without committing the runtime evidence. Raw evidence remains available locally for audit and a separately reviewed future evidence export; none was deleted or modified.

The workspace root currently has no Git repository. No actual staging, commit, branch, remote access, merge, or push was performed. A local isolated bare Git directory under `.runtime/task3_stage5/` was used only to verify ignore patterns. The nested `src/unitree_go2_ros2/.git` is unrelated and must not be accidentally staged as part of Task 3.

## Must stay local

- Real API keys and `~/.config/go2_vlm/credentials.env`; each teammate supplies their own credentials. The external credentials file was not read during handoff.
- `.env`, `.env.*` except `.env.example`, credential/secret files, private key files, and secret directories.
- `build/`, `install/`, `log/`, `.ros/`, `__pycache__/`, `.pytest_cache/`, Python bytecode, egg metadata and coverage output.
- `.runtime/`, including saved runtime images, query logs, the full formal evaluation dataset/results/review packet, one-shot runner locks, historical scratch data and Stage 5 build/test output. Keep the evaluation evidence; do not force-add the whole runtime directory or delete it yet.
- Gazebo caches. `.gz/go2_camera_gui.config` is explicitly exempted from the cache ignore rule because the existing simulation launcher needs it; it is a pre-existing shared simulation dependency, not a Task 3 implementation change.

Historical `scripts/gemini_frozen_once.py` is not needed for normal operation or this handoff; it remains local unless independently reviewed as historical tooling. Do not include unrelated Task 2/Task 4 or simulation implementation changes in the Task 3 integration.

## Integration checklist for teammates

Task 2: call `/go2_vlm/query` using `go2_vlm_interfaces/srv/QueryScene`, `mode=describe`, provider `openai` or `gemini`, and `refresh_frame=true`. Check success, display answer, and retain scene_id. Follow up using `mode=vqa`, a nonempty question, that exact scene_id and `refresh_frame=false`. Never silently replace an expired ID; handle `SCENE_NOT_FOUND` and request a fresh image deliberately. See the README for exact CLI calls and every request/response field.

Task 4: consume success/error_message to gate use, answer as unstructured visual evidence, scene_id/image_stamp/frame_id for image provenance, and provider/model/latency_sec/usage_json for diagnostics. No target pose, bounding box, depth, navigation decision, object approach, or `/cmd_vel` output is provided. Task 4 grounding/object selection and motion are outside Task 3 and were not implemented.

Credentials: use the README's `mkdir -p`, directory mode 700, local `credentials.env` editor, and file mode 600 instructions. Store exported OPENAI_API_KEY/GEMINI_API_KEY assignments only in that local file. Loading keys does not enable cloud calls; the committed default is false.

Build/runtime: `cd ~/go2_jazzy_ws`, source ROS Jazzy, `colcon build --symlink-install`, source install/setup.bash, and use domain 42 consistently. Start the existing apartment/Go2 launcher and one `ros2 launch go2_vlm_scene scene.launch.py`. A valid disabled query returns EXTERNAL_API_DISABLED. The README gives explicit runtime-only enabling commands and portable direct launch commands. No evaluation dataset is needed.

Portability: the existing Jazzy/credential/simulation wrappers embed `/home/briansyc/go2_jazzy_ws`. The credential-launcher tests also depend on those shared wrappers. This path dependency was documented and preserved, not silently refactored. Teammates using another home/path can use the direct runtime commands; portable helper/test setup requires a separate reviewed change. The Python OpenAI SDK/httpx are environment prerequisites for enabled requests and mocked provider tests; package.xml currently does not provision that SDK. No dependency download occurred during Stage 5.

## Final offline regression

An isolated offline symlink build completed successfully for both Task 3 packages (2 packages, 7.47 seconds); the original workspace build/install outputs were not replaced.

The complete existing Task 3 pytest suite passed: **111 passed, 0 failures, 0 errors, 0 skipped**, in 3.11 seconds. Tests exercised capture/retention, ROS services and same-image VQA, both active providers and legacy compatibility, transient retry bounds, disabled defaults, credential permission/tracing protection, redaction and offline evaluation logic.

The run used ROS_DOMAIN_ID=43, localhost-only DDS, a verified inherited kernel `connect` denial, and the suite's autouse Python socket/DNS block. HTTP providers were mocked; only local DDS communication was permitted by the test setup. Real keys were removed from the test environment and credential tests used temporary dummy values. No external API requests were made. The captured test log contains none of the tested credential sentinel values. No credentials were opened or exposed.

AST inspection found **zero create_publisher calls in Task 3 production Python**; ROS integration tests also verify scene_server has no `/cmd_vel` publisher. `enable_external_api_calls: false` and the placeholder-only `.env.example` remain intact. Ignore rules were exercised through Git, including credential/cache exclusions and the `.env.example` exception. The only credential-shaped scan match is a pre-existing synthetic key in the mocked Qwen HTTP-error test; it is absent from test output. No real key was found in the commit candidates.

SHA-256 comparison against the pre-handoff snapshot confirms unchanged runtime implementation, interfaces, tests, protected simulation sources and all formal evaluation evidence. Only README, package ignore rules and setup.py's documentation install entry changed among snapshotted files; new documentation and workspace ignore entries complete the handoff. Full local verification details, hashes, JUnit XML and logs are in `.runtime/task3_stage5/` and should not be committed.

Stop after handoff preparation: no paid rerun, Task 2/4 implementation change or robot operation is part of this stage.
