"""Serve camera views, dialogue history, and manual controls in a browser."""

from collections import deque
from pathlib import Path
from threading import Event, RLock, Thread
import time

import cv2
import rclpy
from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import Twist
from rclpy.node import Node
from ros_gz_interfaces.srv import ControlWorld
from sensor_msgs.msg import Image
from std_msgs.msg import Float32, String
from std_srvs.srv import SetBool
from rclpy.qos import qos_profile_sensor_data
from vision_msgs.msg import Detection2D

from vlm_go2_control.dashboard_http import DashboardHTTPServer


INACTIVE_ARROW_COLOR = (100, 140, 100)  # Muted green in OpenCV BGR order.
ACTIVE_ARROW_COLOR = (0, 255, 0)
VELOCITY_DEADBAND = 1e-3
DETECTION_DISPLAY_SECONDS = 3.0


def draw_velocity_arrows(frame, command):
    """Draw command direction arrows along the four image edges."""
    height, width = frame.shape[:2]
    scale = min(width, height)
    margin = max(6, round(scale * 0.04))
    length = max(18, round(scale * 0.13))
    thickness = max(3, round(scale * 0.015))
    center_x, center_y = width // 2, height // 2
    arrows = (
        ((center_x, margin + length), (center_x, margin),
         command.linear.x > VELOCITY_DEADBAND),
        ((center_x, height - margin - length), (center_x, height - margin),
         command.linear.x < -VELOCITY_DEADBAND),
        ((margin + length, center_y), (margin, center_y),
         command.angular.z > VELOCITY_DEADBAND),
        ((width - margin - length, center_y), (width - margin, center_y),
         command.angular.z < -VELOCITY_DEADBAND),
    )
    for start, tip, active in arrows:
        color = ACTIVE_ARROW_COLOR if active else INACTIVE_ARROW_COLOR
        cv2.arrowedLine(frame, start, tip, color, thickness,
                        line_type=cv2.LINE_AA, tipLength=0.45)


class RobotDashboard(Node):
    """Connect the browser dashboard to the robot's ROS interfaces."""

    def __init__(self):
        super().__init__('robot_dashboard')

        self.image_topic = self.declare_parameter(
            'image_topic', '/rgb_image').value
        self.bounding_box_topic = self.declare_parameter(
            'bounding_box_topic', '/ground_bbox').value
        self.bridge = CvBridge()
        self.state_lock = RLock()
        self.control_lock = RLock()
        self.frames = {}
        self.frame_times = {}
        self.chat_history = deque(maxlen=200)
        self.message_id = 0
        self.manual_enabled = False
        self.simulation_started = False
        self.simulation_paused = True
        self.simulation_pausing = False
        self.teleop_command = Twist()
        self.teleop_deadline = 0.0
        self.teleop_active = False
        self.command_sequences = {}
        self.linear_speed = float(self.declare_parameter('linear_speed', 0.35).value)
        self.angular_speed = float(self.declare_parameter('angular_speed', 0.5).value)
        if not (0.0 < self.linear_speed <= 1.0 and 0.0 < self.angular_speed <= 1.5):
            raise ValueError('Invalid teleoperation speed limits')
        self.command_publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.request_publisher = self.create_publisher(String, '/vlm/user_request', 10)
        self.manual_client = self.create_client(SetBool, '/vlm/manual_control')
        world_name = self.declare_parameter('world_name', 'greenquartz_bto').value
        self.world_control_client = self.create_client(
            ControlWorld, f'/world/{world_name}/control')

        self.image_subscription = self.create_subscription(
            Image, self.image_topic, self.image_callback, qos_profile_sensor_data)
        self.create_subscription(
            Image, '/top_down/image_raw', self.top_down_callback, qos_profile_sensor_data)
        self.create_subscription(
            String, '/vlm/user_request', lambda msg: self.add_message('user', msg.data), 10)
        self.create_subscription(
            String, '/vlm/reply', lambda msg: self.add_message('assistant', msg.data), 10)
        self.create_subscription(
            Detection2D,
            self.bounding_box_topic,
            self.bounding_box_callback,
            10,
        )
        self.front_distance_subscription = self.create_subscription(
            Float32,
            '/front_distance',
            self.front_distance_callback,
            10,
        )
        self.create_subscription(Twist, '/cmd_vel', self.velocity_callback, 10)

        self.latest_detection = None
        self.latest_detection_received_at = None
        self.front_distance = None
        self.latest_velocity = Twist()
        self.create_timer(0.05, self.publish_teleop)
        host = self.declare_parameter('http_host', '127.0.0.1').value
        port = self.declare_parameter('http_port', 8080).value
        page = Path(get_package_share_directory('vlm_go2_control')) / 'web/robot_dashboard.html'
        self.http_server = DashboardHTTPServer((host, port), self, page.read_text())
        self.http_thread = Thread(target=self.http_server.serve_forever, daemon=True)
        self.http_thread.start()
        self.get_logger().info(f'Robot dashboard: http://{host}:{self.http_server.server_port}')

    def add_message(self, role, text):
        """Retain recent conversation messages across browser refreshes."""
        with self.state_lock:
            self.message_id += 1
            self.chat_history.append(dict(id=self.message_id, role=role, text=text))

    def dashboard_state(self):
        with self.state_lock:
            return dict(messages=list(self.chat_history), manual=self.manual_enabled,
                        simulation_started=self.simulation_started,
                        simulation_paused=self.simulation_paused,
                        simulation_ready=self.world_control_client.service_is_ready(),
                        dialogue_online=self.request_publisher.get_subscription_count() > 1,
                        cameras={name: time.monotonic() - stamp < 3.0
                                 for name, stamp in self.frame_times.items()})

    def send_chat(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise ValueError('Enter a message of 1 to 4000 characters.')
        if self.request_publisher.get_subscription_count() <= 1:
            raise RuntimeError('The dialogue manager is not connected.')
        self.request_publisher.publish(String(data=text.strip()))

    def start_simulation(self):
        """Resume Gazebo physics and its simulation clock."""
        self.set_simulation_paused(False)

    def pause_simulation(self):
        """Pause Gazebo physics and its simulation clock."""
        self.set_simulation_paused(True)

    def set_simulation_paused(self, paused):
        """Send a world-control request and update state only when it succeeds."""
        with self.control_lock:
            if paused == self.simulation_paused:
                return
            if not self.world_control_client.wait_for_service(timeout_sec=1.0):
                raise RuntimeError('Gazebo world control is not available yet.')
            if paused:
                # CHAMP holds the last velocity command across a physics pause.
                with self.state_lock:
                    self.simulation_pausing = True
                self.stop_teleop()
            try:
                request = ControlWorld.Request()
                request.world_control.pause = paused
                ready = Event()
                future = self.world_control_client.call_async(request)
                future.add_done_callback(lambda _: ready.set())
                if not ready.wait(10.0):
                    raise RuntimeError('Timed out waiting for Gazebo. Try again.')
                try:
                    response = future.result()
                except Exception as error:
                    raise RuntimeError('Gazebo world control failed.') from error
                if response is None or not response.success:
                    raise RuntimeError('Gazebo did not change the simulation state.')
                with self.state_lock:
                    self.simulation_paused = paused
                    if not paused:
                        self.simulation_started = True
            finally:
                if paused:
                    with self.state_lock:
                        self.simulation_pausing = False

    def set_manual_control(self, enabled):
        """Wait for autonomous motion to stop before enabling manual commands."""
        if not isinstance(enabled, bool):
            raise ValueError('Manual control must be true or false.')
        with self.control_lock:
            if not enabled:
                self.stop_teleop()
                with self.state_lock:
                    self.manual_enabled = False
            if not self.manual_client.wait_for_service(timeout_sec=1.0):
                raise RuntimeError('The dialogue manager is not connected.')
            ready = Event()
            future = self.manual_client.call_async(SetBool.Request(data=enabled))
            future.add_done_callback(lambda _: ready.set())
            if not ready.wait(10.0):
                raise RuntimeError('Timed out waiting for motion to stop. Try again.')
            response = future.result()
            if not response.success:
                raise RuntimeError(response.message)
            with self.state_lock:
                self.manual_enabled = enabled

    def set_direction(self, direction, client_id, sequence):
        """Renew a short command lease while a direction button is held."""
        if (not isinstance(client_id, str) or not 1 <= len(client_id) <= 64 or
                type(sequence) is not int or sequence < 0):
            raise ValueError('Invalid command sequence.')
        directions = {'forward': (self.linear_speed, 0.0),
                      'backward': (-self.linear_speed, 0.0),
                      'left': (0.0, self.angular_speed),
                      'right': (0.0, -self.angular_speed), 'stop': (0.0, 0.0)}
        if direction not in directions:
            raise ValueError('Unknown direction.')
        with self.state_lock:
            # A delayed move request must never override a newer stop request.
            if sequence <= self.command_sequences.get(client_id, -1):
                return
            if client_id not in self.command_sequences and len(self.command_sequences) >= 100:
                raise RuntimeError('Too many browser sessions; restart the dashboard.')
            self.command_sequences[client_id] = sequence
            if direction == 'stop':
                self.stop_teleop()
                return
            if not self.manual_enabled:
                raise RuntimeError('Enable manual control first.')
            if self.simulation_paused or self.simulation_pausing:
                raise RuntimeError('Resume the simulation before driving.')
            linear, angular = directions[direction]
            self.teleop_command = Twist()
            self.teleop_command.linear.x = linear
            self.teleop_command.angular.z = angular
            self.teleop_deadline = time.monotonic() + 0.35
            self.teleop_active = True

    def stop_teleop(self):
        with self.state_lock:
            if self.teleop_active or self.manual_enabled:
                self.command_publisher.publish(Twist())
            self.teleop_active = False
            self.teleop_command = Twist()

    def publish_teleop(self):
        with self.state_lock:
            if not self.teleop_active:
                return
            if time.monotonic() >= self.teleop_deadline:
                self.stop_teleop()
            else:
                self.command_publisher.publish(self.teleop_command)

    def bounding_box_callback(self, message: Detection2D):
        """Store the newest detection and restart its display timeout."""
        with self.state_lock:
            self.latest_detection = message
            self.latest_detection_received_at = time.monotonic()

    def visible_detection(self):
        """Return the current detection only during its display window."""
        if self.latest_detection is None:
            return None
        if (self.latest_detection_received_at is None or
                time.monotonic() - self.latest_detection_received_at >=
                DETECTION_DISPLAY_SECONDS):
            self.latest_detection = None
            self.latest_detection_received_at = None
            return None
        return self.latest_detection

    def front_distance_callback(self, message: Float32):
        """Store the latest forward distance in meters."""
        with self.state_lock:
            self.front_distance = message.data

    def velocity_callback(self, message: Twist):
        """Store the latest command for the next displayed frame."""
        with self.state_lock:
            self.latest_velocity = message

    def image_callback(self, message: Image):
        """Buffer the robot camera for the browser."""
        self.store_image('camera', message)

    def top_down_callback(self, message):
        self.store_image('top-down', message)

    def store_image(self, name, message):
        try:
            frame = self.bridge.imgmsg_to_cv2(message, desired_encoding='bgr8')
        except CvBridgeError as error:
            self.get_logger().error(f'Could not convert image: {error}')
            return
        with self.state_lock:
            self.frames[name] = frame.copy()
            self.frame_times[name] = time.monotonic()

    def camera_jpeg(self, name):
        with self.state_lock:
            if name not in self.frames:
                return None
            frame = self.frames[name].copy()
            if name == 'camera':
                detection = self.visible_detection()
                if detection is not None:
                    self.draw_detection(frame, detection)
                draw_velocity_arrows(frame, self.latest_velocity)
        if frame.shape[1] > 960:
            frame = cv2.resize(frame, (960, round(frame.shape[0] * 960 / frame.shape[1])))
        success, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return encoded.tobytes() if success else None

    def draw_detection(self, frame, detection):
        """Draw one vision_msgs Detection2D on an OpenCV frame."""
        center = detection.bbox.center.position
        width = detection.bbox.size_x
        height = detection.bbox.size_y

        x1 = max(0, round(center.x - width / 2))
        y1 = max(0, round(center.y - height / 2))
        x2 = min(frame.shape[1] - 1, round(center.x + width / 2))
        y2 = min(frame.shape[0] - 1, round(center.y + height / 2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        label = (
            f'{self.front_distance:.2f} m'
            if self.front_distance is not None else '-- m'
        )
        cv2.putText(
            frame,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    def destroy_node(self):
        self.http_server.shutdown()
        self.http_server.server_close()
        self.http_thread.join(timeout=2.0)
        if rclpy.ok():
            self.stop_teleop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    viewer = RobotDashboard()
    try:
        rclpy.spin(viewer)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
