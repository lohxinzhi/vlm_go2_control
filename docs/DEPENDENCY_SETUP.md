# Reproducible Go2 / CHAMP setup

The four project packages use six external packages from one source repository.
The external checkout belongs beside this project in a workspace, outside the
project's Git history. No frozen personal workspace is an underlay or prerequisite.

## Audited source pin and packages

`dependencies.repos` pins
`https://github.com/khaledgabr77/unitree_go2_ros2.git` to
`55ff151632a0220bf3ae0c0772392615d86da7a8`.

| Package | Manifest version | Source |
|---|---|---|
| unitree_go2_sim | 0.0.0 | pinned Unitree repository |
| unitree_go2_description | 0.0.0 | pinned Unitree repository |
| unitree_application | 0.1.0 | pinned Unitree repository |
| champ | 0.1.0 | pinned Unitree repository |
| champ_base | 0.1.0 | pinned Unitree repository |
| champ_msgs | 0.1.0 | pinned Unitree repository |

`champ_base` depends on the bundled `champ` and `champ_msgs`. There is no separate
CHAMP checkout or submodule. Jazzy, Gazebo, ros_gz, gz_ros2_control, ROS controllers,
RealSense description, and standard ROS libraries are system dependencies.

The Task 3 Python package retains `ament_python` as its exported ROS build
 type. In this Jazzy setup it is a build-type identifier, not a rosdep/system
 dependency. The obsolete `<buildtool_depend>ament_python</buildtool_depend>`
entry was removed so normal rosdep resolution can proceed; the
`<export><build_type>ament_python</build_type></export>` declaration remains.

The required audited local patch corrects the simulation manifest dependency
`unitree_applications` to `unitree_application`. Apply it before rosdep. The
reference's optional upstream-launch GUI configuration change is excluded because
the team launch does not use that upstream launch file. Camera Xacro, `/rgb_image`
bridge, CHAMP code, and controller configuration already exist at the pinned commit.

## Fresh workspace

Prerequisites: Ubuntu 24.04, ROS 2 Jazzy and its build tools, Git, Bash, vcstool,
rosdep with initialized rule data, and Python 3 with PyYAML. The helper checks
prerequisites but never installs software, runs rosdep, builds, or launches ROS.
System setup and all network imports are explicit operator actions.

```text
go2_team_ws/
├── src/
│   ├── vlm_go2_control/          # this project; contains four packages in src/
│   └── unitree_go2_ros2/        # independent pinned checkout; six packages
├── build/
├── install/
└── log/
```

Once the integration is published:

```bash
mkdir -p "$HOME/go2_team_ws/src"
cd "$HOME/go2_team_ws/src"
git clone https://github.com/lohxinzhi/vlm_go2_control.git
```

Before continuing, check out the appropriate **published integration revision**
inside `vlm_go2_control`. Until this work is merged, remote main alone is not
sufficient. A local unpublished branch cannot be fetched by teammates. Record the
project commit used alongside the external source pin for a reproducible run.

Import and apply the audited patch explicitly:

```bash
cd "$HOME/go2_team_ws/src/vlm_go2_control"
./scripts/bootstrap_dependencies.bash \
  --workspace "$HOME/go2_team_ws" --apply-patches
```

Equivalent explicit vcstool import, followed by the same patch verification:

```bash
cd "$HOME/go2_team_ws"
vcs import src < src/vlm_go2_control/dependencies.repos
./src/vlm_go2_control/scripts/bootstrap_dependencies.bash \
  --workspace "$HOME/go2_team_ws" --apply-patches
```

Use one import route. The helper does not clone this project and does not fetch
or change existing dependency revisions. It imports only when the external
checkout is absent. Existing wrong revisions, changed origins, unrelated edits,
staged changes, or hidden index flags cause refusal, not a reset or cleanup.

Verify the source checkout before any system dependency resolution or build. This
mode requires no install directory and makes no ROS package-index query:

```bash
./scripts/bootstrap_dependencies.bash \
  --workspace "$HOME/go2_team_ws" --verify-source-only
```

The reproducible sequence is: import dependencies, apply the reviewed patch,
verify source-only, run rosdep, discover/build, source `install/setup.bash`, run
full `--verify-only`, run offline tests, then perform the stationary apartment
smoke test.

Resolve system dependencies after source-only verification:

```bash
cd "$HOME/go2_team_ws"
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src --rosdistro jazzy -y
```

The audited upstream manifests have gaps: `champ` omits build declarations for
ament_cmake/rclcpp; champ/champ_msgs omit ament_lint_auto test declarations;
champ_base/champ_msgs omit ament_cmake buildtool declarations; the simulation
manifest omits some launched packages/controller plugins. Other packages in the
combined workspace cover many of these dependencies, but plugin discovery alone
does not make rosdep infer missing declarations. No untested metadata patch has
been silently added to the audited series.

Explicitly ensure the following system packages are present before building and
smoke testing; if absent, an operator must install them:

```bash
sudo apt install ros-jazzy-ament-lint-auto \
  ros-jazzy-joint-state-broadcaster ros-jazzy-joint-trajectory-controller
```

The robot description declares realsense2_description and gz_ros2_control.
The pinned Velodyne Xacro uses bundled meshes, not an external
velodyne_description package. The upstream README's Gazebo Classic package name
is not this setup's control plugin; this setup uses `ros-jazzy-gz-ros2-control`.

Build from the enclosing workspace, not the nested project checkout:

```bash
cd "$HOME/go2_team_ws"
colcon list
colcon build --symlink-install
source install/setup.bash
./src/vlm_go2_control/scripts/bootstrap_dependencies.bash \
  --workspace "$HOME/go2_team_ws" --verify-only
```

Discovery should contain exactly ten packages: the six external packages above
and go2_house_world, go2_vlm_interfaces, go2_vlm_scene, vlm_go2_control. Resolve any
unexpected duplicates or dependency/build failures before simulation.

## Bootstrap safety and verification

```bash
# Import missing source only. Reports that the patch is not applied.
./scripts/bootstrap_dependencies.bash --workspace /path/to/workspace

# Import if missing, then explicitly apply or recognize the patch.
./scripts/bootstrap_dependencies.bash --workspace /path/to/workspace --apply-patches

# No network, no directory creation, no patching, no Git index writes.
./scripts/bootstrap_dependencies.bash --workspace /path/to/workspace --verify-source-only

# After building and sourcing that workspace's install/setup.bash:
./scripts/bootstrap_dependencies.bash --workspace /path/to/workspace --verify-only
```

`--verify-source-only` reports repository presence, exact source revision, patch
state, and the six package manifests without requiring an installation.
`--verify-only` additionally requires all six packages to be discoverable in the
selected workspace's installed ROS index.

Verification reports repository presence, expected/actual commit, patch state,
source package availability, and package availability in AMENT_PREFIX_PATH.
It returns nonzero for missing/unpatched/wrong source or packages not discoverable
from the selected workspace's installation. Before building/sourcing, a missing
ROS-environment result is expected even if all source packages are present.
A different workspace's package overlay does not count as successful verification.
This checks package index discovery, not runtime controller or camera operation.

Paths with spaces are supported. The helper refuses redirected src/dependency
symlinks and linked dependency worktrees. It refuses writes beneath a path component
named `go2_jazzy_ws`, including canonicalized symlinks, to protect the audited
reference workspace. It refuses imports beneath the project checkout unless the
operator explicitly adds `--allow-project-workspace`; that flag cannot bypass the
reference-workspace protection. The recommended layout never needs this override.

The existing launch wrappers support the enclosing workspace without modification:

```bash
GO2_WORKSPACE="$HOME/go2_team_ws" \
  ./src/vlm_go2_control/scripts/launch_house_go2.bash
```

## Offline regression, then shared apartment smoke test

After the independent build, run existing tests before starting Gazebo:

```bash
cd "$HOME/go2_team_ws"
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export GO2_WORKSPACE="$PWD"
export ROS_DOMAIN_ID=43 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
unset OPENAI_API_KEY GEMINI_API_KEY DASHSCOPE_API_KEY QWEN_BASE_URL
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python3 -m pytest -q src/vlm_go2_control/src/go2_vlm_scene/test
python3 -m pytest -q src/vlm_go2_control/src/go2_house_world/test
(cd src/vlm_go2_control/src/vlm_go2_control && python3 -m pytest -q test)
```

Task 3 tests retain their Python network-blocking fixture and use dummy credentials.
The Python OpenAI SDK/httpx prerequisites for mocked-provider tests remain as
documented in the Task 3 README; no live API request is part of this procedure.

For the separately authorized stationary smoke test:

```bash
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch go2_house_world apartment_go2.launch.py
```

The launch chain is go2_house_world -> the existing team go2_simulation_launch.py
-> ros_gz_sim plus the imported Unitree descriptions/configuration and CHAMP node.
It does not include the optional patched upstream unitree_go2_launch.py. The world
package does not duplicate robot definitions. The inherited team odometry and
controller startup differ from the reference upstream orchestration and still
require runtime verification.

Check apartment geometry, pale oak floor, the five target placements, the Go2
spawn, /rgb_image, /joint_states, and both active controllers. Do not send velocity
commands or run autonomous navigation. Shut the launch down with Ctrl-C. Stage 6B
staging remains pending until this independent verification succeeds.

## Version and licensing limits

Source is pinned, but rosdep does not lock apt binaries. Stage 6C observed
ros_gz 1.0.24, gz_ros2_control 1.2.20, ros2_control/controller_manager 4.48.0,
ROS controllers 4.42.1, robot_localization 3.8.3, realsense2_description 4.58.4,
and xacro 2.1.1. Record actual installed versions for a tested environment;
stronger binary reproducibility requires a separately reviewed image/package lock.

champ, champ_base, champ_msgs, and unitree_application report BSD metadata.
The bundled CHAMP core includes a BSD three-clause license. The inspected
unitree_go2_sim / unitree_go2_description manifests contain TODO license declarations,
and the inspected repository metadata does not establish a clear repository-wide
redistribution licence. Retrieving dependencies from the original repository
avoids vendoring their complete source/assets into this project's Git history;
it does not resolve that licensing ambiguity. Do not describe ambiguous Unitree
assets as Apache-2.0. The apartment-world package retains its existing Proprietary
metadata. No license declaration is changed by this integration.
