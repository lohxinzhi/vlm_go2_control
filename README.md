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
- `slam:=false map:=/absolute/path/to/map.yaml`: use AMCL with a saved map.
- `params_file:=/absolute/path/to/params.yaml`: override the combined Nav2/SLAM settings.
- `use_composition:=false`: run Nav2 servers as separate processes.

Save the map from another sourced terminal:

```bash
ros2 run nav2_map_server map_saver_cli -f /tmp/go2_map --ros-args -p use_sim_time:=true
```

## Interfaces

All source changes reside in this package. The local simulation launch reuses
the upstream Go2 model, CHAMP controllers, gait settings, and body EKF configuration.
It is intended for one robot in the root namespace.

- SLAM Toolbox publishes `map -> odom`.
- CHAMP's two EKFs publish `odom -> base_footprint -> base_link`.
- Gazebo ground-truth odometry is available separately on `/odom/ground_truth`.
- The Gazebo Velodyne scan is bridged to `/scan`, retaining the `velodyne` frame.
  The Jazzy bridge selects the middle vertical beam of the 3D lidar:
  [bridge implementation](https://github.com/gazebosim/ros_gz/blob/jazzy/ros_gz_bridge/src/convert/sensor_msgs.cpp).
  This planar scan is an approximation while the quadruped pitches or rolls.
- Nav2 publishes unstamped `geometry_msgs/msg/Twist` on `/cmd_vel` for CHAMP.
  Forward/backward speed is limited to 0.3 m/s and yaw speed to 0.5 rad/s.
  The controller uses forward motion and turning; lateral motion remains disabled.
- Both costmaps use a conservative 0.8 m by 0.4 m footprint and planar obstacle layers.

The original simulation launch's static map/body transforms and Gazebo TF bridge
are not launched, so they do not compete with SLAM or the EKFs.
The existing point-cloud and camera topics remain available.
Do not launch the upstream simulation separately alongside this launch.
