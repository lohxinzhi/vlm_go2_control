# Stage 6H — controller startup timing and stationary stability

Stage 6H passed the requested stationary stability and interface checks. Go2
remained upright through 75.001 seconds, including more than 42 seconds with the
effort controller active. Only launch timing, its offline regression, and this
validation documentation changed. No gains, gait, Xacro, spawn, physics, camera,
remappings, controller YAML, or velocity behavior were modified.

## Implementation and offline verification

`src/vlm_go2_control/launch/go2_simulation_launch.py` replaces the immediate,
combined controller spawner with two independent wall-clock `TimerAction`s:

- `period=20.0`: `joint_states_controller`.
- `period=30.0`: `joint_group_effort_controller`.

Both retain `--controller-manager-timeout 120`, `parameters=[clock]`, and screen
output. These are the same independent timer semantics used by the imported,
pinned upstream launch. Controller types and parameter files remain unchanged.

`test_controller_startup.py` generates the real launch description with passive
node stand-ins and mocked local package/Xacro resolution. It checks independent
20/30-second timers, exactly two spawners, no immediate spawner, exact names,
timeouts, simulation-clock parameters, and CHAMP/odometry parameter-file wiring.
It starts no processes, DDS participants, or external requests.

| Verification | Result |
| --- | --- |
| Integration scoped `colcon build --symlink-install --packages-select vlm_go2_control` | Passed |
| Integration package tests | 6 passed, 1 pre-existing copyright skip |
| Independent clean `colcon build --symlink-install` | All 10 packages passed, 30.9 s |
| Independent vlm_go2_control tests, including timing regression and linters | 6 passed, 1 pre-existing copyright skip |
| Task 3 offline suite, with network-blocking fixture | 111 passed |
| World source resource tests | 5 passed |
| World installed resource tests | 5 passed |
| Post-build bootstrap `--verify-only` | Passed; all six dependency packages resolved within independent install |

The independent project snapshot was refreshed only from the integration source.
Git metadata, generated build/install/log trees, runtime/ROS directories, caches,
bytecode, secrets, and temporary files were excluded. The already imported
external checkout was preserved. Verification required commit
`55ff151632a0220bf3ae0c0772392615d86da7a8` and an exact diff matching only the
reviewed `unitree_application` patch, with no staged or unrelated untracked edits.
Only `/home/briansyc/go2_team_ws/{build,install,log}` was removed for the clean build.

## Runtime method and measurement limits

Run date: 2026-09-21 Asia/Singapore. The process used a clean environment, sourced
Jazzy and the independent install, and launched:

```bash
ros2 launch go2_house_world apartment_go2.launch.py gui:=false
```

A passive observer subscribed to JointState, camera Image, CHAMP JointTrajectory,
and `/cmd_vel`, polled controller services, and recorded graph counts once per
second. It created no velocity publisher. World poses came directly from Gazebo's
`/world/greenquartz_bto/pose/info`, selecting model `go2`. Pose events were monitored
continuously for an absolute roll or pitch above 0.5 rad, with immediate shutdown
on detection; no threshold crossing occurred. Pose rows were saved once per
second from the first available pose to shutdown. Times are observer monotonic
wall seconds; launch process creation was at 0.035 s. Gazebo pose `stamp=0` in the
raw observer records is a placeholder, not a measured simulation timestamp.

An initial 75-second run collected healthy controllers, joint states, and camera
images but no ROS ground-truth pose, so it was not accepted as stability evidence.
Inspection found an existing mismatch: the external Xacro publishes Gazebo
`/odom/ground_truth`, while the team bridge subscribes to Gazebo `/odom`. No fix was
made. The final validation repeated the unchanged simulation with the direct
Gazebo pose subscriber. This instrumentation correction was not a robot fix;
there was no observed fall triggering the stop-without-further-fixes condition.
ROS ground-truth odometry remains unavailable and is outside this timing-only
change; this report does not certify navigation or odometry operation.

## Final run timing and interfaces

| Event | Elapsed wall seconds |
| --- | ---: |
| Go2 entity creation successful | 1.191 |
| Controller-manager resource initialization complete | 4.366 |
| Controller-manager service ready to observer | 4.367 |
| First measured world pose | 4.968 |
| First RGB image | 7.631 |
| Joint-state spawner process started | 20.584 |
| First JointState sample | 22.102 |
| Joint-state broadcaster configured and activated | 22.103 |
| Effort spawner process started | 30.581 |
| Effort controller configured and activated | 32.458 |
| First non-neutral CHAMP command published to observer | 0.708 |
| First non-neutral command after observer confirmed effort active | 32.472 |
| Observation ended | 75.001 |
| Launch exited after SIGINT | 75.419 |

Actual activation follows the requested 20/30-second spawner scheduling by roughly
1.5/1.9 seconds of process/service discovery and controller configuration. The
timers do not promise exact activation instants. CHAMP already publishes stance
trajectories before activation: approximately hip 0, upper leg 1.01435, lower leg
-2.02871 rad on each leg. The 32.472-second record is the first command observed
after the service poll confirmed activation, not a measurement of the controller's
first internally accepted or hardware-applied command.

- `/joint_states`: one `joint_states_controller` publisher of type
  `sensor_msgs/msg/JointState`, backed by `joint_state_broadcaster/JointStateBroadcaster`.
  All 12 expected joints were present: hip, upper-leg, and lower-leg joints on
  `lf`, `rf`, `lh`, and `rh`. Received 13,125 samples. No additional CHAMP joint-state
  publisher was enabled.
- `/rgb_image`: 647 images, 640 × 480 `rgb8`, continuously received after startup.
  Maximum observed inter-image gap was 0.300 s.
- Controller manager remained responsive; both named controllers remained active
  through the end. The effort controller type was
  `joint_trajectory_controller/JointTrajectoryController`.
- All 12 effort command interfaces were available and claimed by the effort
  controller. All 24 position/velocity state interfaces were available. Their
  reported `is_claimed=false` is the service's state-interface reporting, not a
  missing effort command claim.
- Every once-per-second graph observation reported zero `/cmd_vel` publishers;
  the subscriber received zero `/cmd_vel` messages. No VLM/API calls were made.

## Pose evolution and acceptance

Full one-second measurements: [STAGE_6H_POSES.csv](STAGE_6H_POSES.csv).
Raw graph, controller, hardware, command, and pose evidence:
[STAGE_6H_RUNTIME.jsonl](STAGE_6H_RUNTIME.jsonl).

| Wall time | XYZ (m) | RPY (rad) |
| --- | --- | --- |
| 4.968 | 3.100000, 4.402111, 0.375001 | -0.000000, 0.000000, 1.570796 |
| 10 | 3.100000, 4.578544, 0.282231 | 0.000000, 0.000206, 1.570796 |
| 20 | 3.100000, 4.578547, 0.291940 | 0.000000, 0.000214, 1.570796 |
| 30 | 3.100000, 4.578550, 0.301614 | 0.000000, 0.000223, 1.570796 |
| 40 | 3.101103, 4.557684, 0.239024 | 0.000148, -0.000983, 1.575548 |
| 50 | 3.101107, 4.557703, 0.239048 | 0.000163, -0.001010, 1.575568 |
| 60 | 3.101108, 4.557699, 0.239037 | 0.000164, -0.001001, 1.575588 |
| 70 | 3.101105, 4.557712, 0.239059 | 0.000150, -0.001015, 1.575607 |
| 75.001 | 3.101104, 4.557706, 0.239063 | 0.000148, -0.001017, 1.575616 |

Maximum absolute roll/pitch in one-second samples was 0.00272/0.02342 rad.
Go2 remained upright during initial settling, broadcaster activation, effort
activation, and subsequent non-neutral stance commands. No rapid falling
excursion occurred. The small translation is passive settling/stance acquisition,
with no locomotion commands. After 40 seconds, the pose was essentially stationary.

The Stage 6G reference settled at approximately XYZ 3.100, 4.564, 0.240 and
RPY 0.000, -0.002, 1.570. The final team position differs by approximately
+1.1 mm, -6.3 mm, -0.9 mm and remains upright, meeting the requested qualitative
stationary comparison.

The specified Stage 6B/6E stationary simulation smoke requirements are now
satisfied: independent build/dependency verification, world resource/install
checks, stable Go2, camera, joints, controllers, and hardware claims. This does
not certify unrelated navigation/odometry functionality or a GUI visual review;
the headless run used offline resource checks for apartment assets and targets.

## Shutdown and integrity

SIGINT shut down the launch and its simulation processes; launch returned 0.
Some children were reported as interrupted with exit -2 during group SIGINT.
No forced termination was needed. Post-run inspection found no stale Gazebo,
controller, robot-state-publisher, bridge, odometry, or launch processes.

Before/after content manifests confirmed Task 3 source, world assets, and every
other pre-existing integration source file unchanged except the intended launch.
The frozen reference source/Git manifest was unchanged; no commands wrote to or
copied from that workspace. The integration Git index was unchanged. Nothing was
staged, committed, or pushed. Work stopped after Stage 6H.

Raw build/test logs, both run logs, integrity manifests, and the passive recorder
are retained locally under `/tmp/stage6h`.
