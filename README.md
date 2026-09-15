# Go2 simulation with Nav2 and SLAM

Build and launch from the workspace:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install --packages-select vlm_go2_control
source install/setup.bash
ros2 launch vlm_go2_control go2_sim_nav2_launch.py
```

The default is online SLAM in TIbuilding.sdf, with Gazebo and RViz.
Wait for the controllers and Nav2 to activate, then use RViz's Nav2 Goal
tool to navigate through mapped free space. Mapping continues while moving;
this launch does not perform autonomous frontier exploration.

Options:

- `gui:=false use_rviz:=false`: run without the Gazebo GUI or RViz.
- `world:=/absolute/path/to/world.sdf`: select another world.
  Set the spawn coordinates to match its floor height; for the upstream
  `default.sdf`, use `world_init_z:=0.375`. TIbuilding uses `4.375`.
- `ground_height:=4.0`: floor elevation in Gazebo world coordinates.
  Defaults to `world_init_z - 0.375`; override it if spawning above the normal height.
- `slam:=false map:=/absolute/path/to/map.yaml`: use AMCL with a saved map.
- `params_file:=/absolute/path/to/params.yaml`: override the combined Nav2/SLAM settings.
- `use_composition:=false`: run Nav2 servers as separate processes.

Save the map from another sourced terminal:

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
