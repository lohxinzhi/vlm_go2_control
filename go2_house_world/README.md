# Shared apartment simulation

## Overhead camera

The world includes a fixed, top-down orthographic camera covering 36 m by
24 m. Its Gazebo image topic is `/top_down/image`; the one-way ROS bridge
publishes `sensor_msgs/msg/Image` on `/top_down/image_raw` at 5 Hz.

To start the world and bridge together:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch go2_house_world greenquartz_bto_camera.launch.py
```

When another launch already starts this world and the Go2, start only the
camera bridge in a second terminal:

```bash
ros2 launch go2_house_world top_down_camera_bridge.launch.py
```

GreenQuartz is the intended shared project world. This package contains the
apartment mesh, pale oak floor texture, 249 simplified collision boxes, and
five static coloured targets. Runtime assets are preserved from the working
apartment implementation; the original asset package's Proprietary license
metadata is retained separately from the team code's Apache-2.0 license.

## Build and launch

From the repository root, source ROS 2 Jazzy and any independently installed
team robot dependency underlay, then build:

```bash
source /opt/ros/jazzy/setup.bash
# source /path/to/team_dependencies/install/setup.bash  # if needed
colcon build --symlink-install
source install/setup.bash
export ROS_DOMAIN_ID=42 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch go2_house_world apartment_go2.launch.py
```

`./scripts/launch_house_go2.bash` is a convenience entry point when dependencies
are available in the environment sourced by `jazzy_exec.bash`. The Stage 6A
wrapper deliberately clears inherited overlays; use the direct launch above
when robot dependencies require a separate underlay.

Dependencies include ROS Jazzy/Gazebo Harmonic, `ros_gz_sim`, and the existing
`vlm_go2_control` simulation dependencies, including `unitree_go2_sim`,
`unitree_go2_description`, `champ_base`, `ros_gz_bridge`, `gz_ros2_control`,
and ROS controllers. These robot dependencies must be installed independently;
this package does not vendor them or refer to another personal workspace.
No dependency download occurs at launch.

The new launch includes the existing `go2_simulation_launch.py` unchanged.
It preserves that launch's controller/camera/odometry stack and sets the world
using the installed `go2_house_world` package share directory. It prepends the
installed `models/` directory to `GZ_SIM_RESOURCE_PATH`; all world, OBJ, MTL,
texture and target references resolve within the package. No Fusion export,
Downloads folder, saved personal GUI configuration, or external asset is needed.
The world's embedded Gazebo GUI provides the apartment overview.

The intended spawn is XYZ `(3.10, 4.40, 0.375)` metres, roll/pitch zero,
yaw `1.5707963267948966` radians. Defaults live in
`launch/apartment_go2.launch.py`; override `world_init_x`, `world_init_y`,
`world_init_z`, or `world_init_heading` explicitly if needed. Ground height
is zero. `gui:=false` is available for headless use. The launch sends no
velocity commands and does not start Nav2 or a VLM server. Existing team
simulation and Nav2 launch entry points remain available unchanged.

## Preserved targets

| Target | Room | XYZ (m) | RPY (rad) |
|---|---|---|---|
| Green cube | Living room | 3.10, 6.10, 0.150 | 0, 0, 0 |
| Red triangular prism | Bedroom 1 | 7.00, 5.80, 0.175 | 0, 0, 0 |
| Blue cylinder | Bedroom 2 | 10.00, 5.80, 0.175 | 0, 0, 0 |
| Yellow cube | Master bedroom | 13.20, 5.80, 0.150 | 0, 0, 0 |
| Purple cylinder | Kitchen | 4.70, -0.50, 0.175 | 0, 0, 0 |

World include poses live in `worlds/greenquartz_bto.sdf`. Definitions live in
`models/target_*/model.sdf`. The red prism uses `meshes/triangle.dae` for both
visual and collision geometry. The other targets use primitives. Their bottoms
sit at Z=0; they remain static, matte, and opaque. Apartment mesh scaling is
0.01 and the apartment model offset is Z=-0.01, unchanged from the working setup.

## Runtime assets versus development artifacts

Runtime-required: `models/` (six model configurations/SDFs, apartment OBJ/MTL,
pale oak PNG, triangular-prism DAE), `worlds/greenquartz_bto.sdf`, and the new
launch entry point. Build metadata installs these assets.

Not transferred: original `verification/` screenshots, geometry NPZ, JSON/text
reports; original `tools/` geometry generation/verification scripts and personal
launcher; older README/GO2_INTEGRATION/TARGETS documents with obsolete launch
instructions and historical results. Source CAD exports are not runtime inputs.

`test/test_world_resources.py` checks resource closure, floor texture references,
all target poses, floor support/collision separation, room bounds, and absence
of personal runtime paths. It can also check installed resources by setting
`GO2_HOUSE_WORLD_SHARE` to the installed share directory before invoking pytest.
These offline checks do not replace the stationary Gazebo/controller smoke test.
