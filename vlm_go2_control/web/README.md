# Go2 robot dashboard

Start Gazebo/navigation as usual, then run from the workspace:

```bash
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 launch vlm_go2_control dashboard_and_dialogue.launch.py
```

Open **http://127.0.0.1:8080** in a browser on the same machine. This launch starts
the dialogue manager, action/service servers, dashboard, and
`go2_house_world/top_down_camera_bridge.launch.py`, plus the Gazebo world-control
bridge. When using `go2_sim_nav2_launch.py`, click **Start simulation** to resume
physics and simulation time before navigating. The button then switches to
**Pause simulation** and **Resume simulation**. Pausing stops active dashboard
velocity commands. The OpenAI key must be available
to the dialogue and perception nodes as before.

If the dialogue manager and action servers are already running, launch only the
dashboard and top-down bridge:

```bash
ros2 launch vlm_go2_control robot_dashboard.launch.py
```

Use `http_port:=8081` on either launch command to choose another port. If the
simulation uses a different SDF world, also set `world_name:=<SDF world name>`
on the dashboard launch. The new
node/executable is `robot_dashboard`; `show_img` remains an executable alias.

The robot camera uses `/rgb_image`, with the existing velocity arrows and
three-second bounding box timeout. The overhead view uses `/top_down/image_raw`.
Both panels indicate when camera updates stop arriving.

Send messages using the conversation panel. Requests go to `/vlm/user_request`;
the dialogue manager publishes replies on `/vlm/reply`. The latest 200 messages
are held in memory and survive browser refreshes, but reset when the dashboard
node restarts.

Click **Take manual control** before driving. This asks the dialogue manager to
cancel active motion and waits for it to finish. Hold a direction button, or use
the keyboard arrow keys when the message field is not focused. Releasing the
button/key, clicking STOP, switching windows, or losing command updates stops
manual movement. The server expires a command after 0.35 seconds without a
refresh. Default speeds are 0.35 m/s forward/backward and 0.5 rad/s turning.

Click **Release manual control** before asking the dialogue manager to move
again. Scene questions and other non-motion dialogue remain available during
manual control. Manual mode remains selected if the browser closes; reopen the
dashboard to release it. Control coordinates only the dialogue manager's
actions; other independent `/cmd_vel` publishers should not drive simultaneously.
