# Go2 simulation with Nav2 and robot dashboard

This repository contains the `vlm_go2_control`, `vlm_go2_interfaces`, and
`go2_house_world` ROS 2 packages. The navigation launch starts one Go2 in the
GreenQuartz apartment with Gazebo, Nav2, a saved map, and RViz. The dashboard
has its own launch command and shows robot and overhead cameras, conversation,
and manual controls.

## Requirements and setup

- Ubuntu 24.04 with ROS 2 Jazzy and Gazebo Harmonic.
- The [Unitree Go2 ROS 2 Jazzy simulation](https://github.com/RobInLabUJI/unitree_go2_ros2_jazzy)
  source packages (including `unitree_go2_sim`, `unitree_go2_description`, and
  `champ_base`).
- Nav2, SLAM Toolbox, ROS–Gazebo integration, ROS 2 controllers, and the other
  ROS dependencies declared in the packages' `package.xml` files.
- Python 3.12 with `python3-pip` (`python3-venv` if using a virtual environment).
  `requirements.txt` includes the OpenAI client and a NumPy version compatible
  with Jazzy's `cv_bridge`.
- An OpenAI API key for dialogue and vision requests. The camera-only dashboard
  can start without one; dialogue and coordinated manual control require its
  dialogue stack.

Create a ROS 2 workspace and clone the package and Go2 simulation sources:

```bash
source /opt/ros/jazzy/setup.bash
mkdir -p ~/go2_ws/src
cd ~/go2_ws/src
git clone https://github.com/lohxinzhi/vlm_go2_control.git
git clone https://github.com/RobInLabUJI/unitree_go2_ros2_jazzy.git
cd ~/go2_ws
sudo apt install python3-pip python3-rosdep ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup ros-jazzy-slam-toolbox
rosdep update
rosdep install --from-paths src/vlm_go2_control src/unitree_go2_ros2_jazzy \
  --ignore-src -r -y
```

Choose one way to install the Python requirements. For an isolated virtual
environment that can still access ROS's system Python packages:

```bash
sudo apt install python3-venv
./src/vlm_go2_control/setup_venv.sh
source src/vlm_go2_control/.venv/bin/activate
```

Or use the main Python interpreter without a virtual environment:

```bash
python3 -m pip install --user --break-system-packages \
  -r src/vlm_go2_control/requirements.txt
```

Ubuntu 24.04 requires `--break-system-packages` for pip installs into its
system-managed Python. `--user` keeps these packages in your user directory.

Then build the workspace:

```bash
python3 -m colcon build --symlink-install --packages-up-to vlm_go2_control
source install/setup.bash
```

If the workspace already has the Go2 or Nav2 sources, keep those sources and
build them in the same overlay. If you chose the virtual environment, activate
it before building and in each new launch terminal with
`source src/vlm_go2_control/.venv/bin/activate`.

## Launch simulation and navigation

In terminal 1:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/go2_ws
source install/setup.bash
ros2 launch vlm_go2_control go2_sim_nav2_launch.py
```

Gazebo starts paused, so physics and `/clock` do not advance yet. Start the
dashboard below and click **Start simulation** when ready. Then wait for the
controllers and Nav2 to activate and use RViz's Nav2 Goal tool to navigate.
The default uses the included `maps/bto_1.yaml` with AMCL. Start
online mapping with `slam:=true`; mapping continues while the robot moves.
This launch does not perform autonomous frontier exploration.

## Launch the robot dashboard

In terminal 2, after starting the simulation, launch the dashboard and its
dialogue/action servers. Set the API key in this terminal if using VLM requests:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/go2_ws
source install/setup.bash
export OPENAI_API_KEY='your-api-key'
ros2 launch vlm_go2_control dashboard_and_dialogue.launch.py
```

Open <http://127.0.0.1:8080> on the same machine. The launch also starts the
overhead camera and Gazebo world-control bridges. Click **Start simulation** to
resume physics and simulation time. The button then changes to **Pause simulation**;
click it to stop physics and simulation time, then **Resume simulation** to continue.
Use the conversation panel for VLM requests. To drive
with the dashboard, click **Take manual control**; click **Release manual control**
before requesting robot motion through dialogue again. If you only need the
camera views and dashboard, run
`ros2 launch vlm_go2_control robot_dashboard.launch.py` instead; the dialogue
and action servers will not be started. See the [dashboard guide](vlm_go2_control/web/README.md)
for control details. Do not start both dashboard launch files together.

Simulation and navigation options:

- `gui:=true`: show the Gazebo GUI (off by default).
- `paused:=false`: start Gazebo running immediately without the dashboard button.
- `use_rviz:=false`: run without RViz.
- `world:=/absolute/path/to/world.sdf`: select another world.
  Set `world_init_x`, `world_init_y`, `world_init_z`, and `world_init_heading`
  to a valid pose for that world. Pass `world_name:=<SDF world name>` to the
  dashboard launch so its Start button controls the selected world.
- `slam:=true`: build a map online with SLAM Toolbox.
- `map:=/absolute/path/to/map.yaml`: use another saved map with the default
  `slam:=false` mode.
- `params_file:=/absolute/path/to/params.yaml`: override the combined Nav2/SLAM settings.
- `use_composition:=false`: run Nav2 servers as separate processes.

When using `slam:=true`, save the map from another sourced terminal:

```bash
ros2 run nav2_map_server map_saver_cli -f /tmp/go2_map --ros-args -p use_sim_time:=true
```

## Interfaces

All source changes reside in this package. The local simulation launch reuses
the upstream Go2 model, CHAMP controller, and gait settings.
It is intended for one robot in the root namespace.

- SLAM Toolbox publishes `map -> odom`.
- The `simulation_odometry` node publishes `/odom` and
  `odom -> base_footprint -> base_link`, using measured Gazebo motion.
  The footprint carries planar position/yaw; the body transform retains measured
  height above the floor and roll/pitch at the same simulation timestamp.
- Gazebo 3D ground-truth odometry is available on `/odom/ground_truth`.
  The launch enables 3D odometry in the generated robot description in memory.
  Upstream model source files remain unchanged.
- The Gazebo Velodyne scan is bridged to `/scan`, retaining the `velodyne` frame.
  The Jazzy bridge selects the middle vertical beam of the 3D lidar:
  [bridge implementation](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/src/convert/sensor_msgs.cpp).
  This planar scan is an approximation while the quadruped pitches or rolls.
- Nav2 publishes unstamped `geometry_msgs/msg/Twist` on `/cmd_vel` for CHAMP.
  Forward/backward speed is limited to 0.3 m/s and yaw speed to 0.5 rad/s.
  The controller uses forward motion and turning; lateral motion remains disabled.
- Both costmaps use a conservative 0.8 m by 0.4 m footprint and planar obstacle layers.

The original simulation launch's static map/body transforms and Gazebo TF bridge
are not launched, so they do not compete with SLAM or simulation odometry.
The existing point-cloud and camera topics remain available.
Do not launch the upstream simulation separately alongside this launch.

## Controller and topic checks

The simulated model has no foot-contact publisher. CHAMP's leg-state estimator
requires those contacts together with joint states, so using it here produced
zero forward odometry even when the robot moved. Simulation odometry uses Gazebo
measurements instead; this is a simulation-only setup, not a hardware estimator.

The controller spawner waits for `/controller_manager` as soon as the launch
starts. Wait until both controllers report `active`:

```bash
ros2 control list_controllers
ros2 topic info /joint_group_effort_controller/joint_trajectory --verbose
ros2 topic info /joint_states --verbose
ros2 topic info /odom --verbose
```

Expected connections:

| Topic | Publisher | Consumer |
| --- | --- | --- |
| `/cmd_vel_nav` | Nav2 controller/behaviors | Velocity smoother |
| `/cmd_vel_smoothed` | Velocity smoother | Collision monitor |
| `/cmd_vel` | Collision monitor (or manual commands) | CHAMP |
| `/joint_group_effort_controller/joint_trajectory` | CHAMP | ROS joint trajectory controller |
| `/joint_states` | Joint state broadcaster | Robot state publisher |
| `/odom/ground_truth` | Gazebo bridge | Simulation odometry |
| `/odom` | Simulation odometry | Nav2 |
| `/scan` | Gazebo bridge | SLAM and costmaps |

The trajectory controller uses ROS messages directly and writes effort commands
through `gz_ros2_control`; a Gazebo JointTrajectory bridge is unnecessary.
For manual motion, with no active navigation goal, publish unstamped Twist:

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.1}}'
# After stopping that publisher, explicitly stop the robot:
ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{}'
```

CHAMP retains the last velocity command, so stopping the publisher alone does
not stop the robot. Publishers sending TwistStamped must use an adapter or be
configured to publish Twist.
