"""Ground an object in camera frames and approach it through an action."""

import base64
import json
import math
import os
import time
from threading import Event, Lock

import cv2
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from openai import OpenAI
from std_srvs.srv import Trigger
from vision_msgs.msg import Detection2D

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from vlm_go2_interfaces.action import ApproachObject

from vlm_go2_control.vlm_dialogue_manager import Camera


SEARCH_SPEED = 0.3  # radians per second, counterclockwise
SEARCH_STEP = math.radians(30.0)
# Leave room for stopping after the final command so the turn stays under 360 degrees.
MAX_SEARCH_ROTATION = 2.0 * math.pi - math.radians(15.0)


class ApproachObjectServer(Node):
    """Run the bounded camera guided approach loop and return its result."""

    def __init__(self, camera):
        super().__init__('approach_object_server')
        self.camera = camera

        self.client_type = self.declare_parameter(
            'client_type', 'openai').value.lower()
        if self.client_type == 'openai':
            self.client = OpenAI()
            self.vlm_model = self.declare_parameter(
                'vlm_model', 'gpt-5.6-luna').value.lower()
        elif self.client_type == "qwen":
            self.client = OpenAI(
                api_key=os.environ.get('QWEN_API_KEY'),
                base_url=os.environ.get('QWEN_BASE_URL'))
            self.vlm_model = self.declare_parameter(
                'vlm_model', 'qwen3.5-flash').value.lower()
        self.stop_requested = Event()
        self.goal_lock = Lock()
        self.busy = False
        self.filter_alpha = 0.25
        self.filtered_cmd = Twist()
        self.current_yaw = None
        self.last_odom_received_at = None
        self.velocity_publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.bbox_publisher = self.create_publisher(
            Detection2D, '/ground_bbox', 10)
        group = ReentrantCallbackGroup()
        self.create_subscription(
            Odometry, '/odom', self.odom_callback, 10,
            callback_group=group)
        self.server = ActionServer(
            self, ApproachObject, '/approach_object', self.execute,
            goal_callback=self.accept_goal, cancel_callback=self.cancel_goal,
            callback_group=group)
        self.stop_service = self.create_service(
            Trigger, '/stop_approach', self.stop, callback_group=group)

    def accept_goal(self, request):
        with self.goal_lock:
            if self.busy or not request.object_name.strip():
                return GoalResponse.REJECT
            self.busy = True
            self.stop_requested.clear()
        return GoalResponse.ACCEPT

    def cancel_goal(self, _goal_handle):
        self.stop_requested.set()
        return CancelResponse.ACCEPT

    def stop(self, _request, response):
        self.stop_requested.set()
        self.filtered_cmd = Twist()
        self.velocity_publisher.publish(self.filtered_cmd)
        response.success = True
        response.message = 'Stopped.'
        return response

    def apply_low_pass_filter(self, command):
        filtered = Twist()
        filtered.linear.x = (
            self.filter_alpha * command.linear.x +
            (1.0 - self.filter_alpha) * self.filtered_cmd.linear.x)
        filtered.angular.z = (
            self.filter_alpha * command.angular.z +
            (1.0 - self.filter_alpha) * self.filtered_cmd.angular.z)
        self.filtered_cmd = filtered
        return filtered

    def odom_callback(self, message):
        """Keep the latest measured yaw for the bounded search turn."""
        q = message.pose.pose.orientation
        self.current_yaw = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z))
        self.last_odom_received_at = time.monotonic()

    def canceled(self, goal_handle):
        return self.stop_requested.is_set() or goal_handle.is_cancel_requested

    def wait_for_new_frame(self, after_time, goal_handle):
        """Capture an image taken after the robot stops turning."""
        deadline = time.monotonic() + 2.0
        while rclpy.ok() and time.monotonic() < deadline:
            if self.canceled(goal_handle):
                return None
            received_at = self.camera.frame_received_at
            if received_at is not None and received_at > after_time:
                return self.camera.frame
            Event().wait(0.05)
        raise RuntimeError('No new camera frame arrived during the search')

    def search_for_object(self, object_name, goal_handle):
        """Check new views while turning at most once around the robot's yaw."""
        if (self.current_yaw is None or self.last_odom_received_at is None or
                time.monotonic() - self.last_odom_received_at > 1.0):
            raise RuntimeError('Fresh odometry is required for a bounded search')

        self.filtered_cmd = Twist()
        self.velocity_publisher.publish(Twist())
        previous_yaw = self.current_yaw
        rotation = 0.0
        while (rotation < MAX_SEARCH_ROTATION - 0.04 and
               not self.canceled(goal_handle)):
            # Stop short of each target to allow for controller and robot inertia.
            target = min(rotation + SEARCH_STEP, MAX_SEARCH_ROTATION)
            command = Twist()
            command.angular.z = SEARCH_SPEED
            deadline = time.monotonic() + 3.0 * SEARCH_STEP / SEARCH_SPEED
            try:
                while rotation < target - 0.04 and not self.canceled(goal_handle):
                    if time.monotonic() > deadline:
                        raise RuntimeError('Search rotation did not follow odometry')
                    if (self.last_odom_received_at is None or
                            time.monotonic() - self.last_odom_received_at > 1.0):
                        raise RuntimeError('Odometry stopped during search')
                    self.velocity_publisher.publish(command)
                    Event().wait(0.05)
                    yaw = self.current_yaw
                    change = math.atan2(
                        math.sin(yaw - previous_yaw),
                        math.cos(yaw - previous_yaw))
                    rotation += max(0.0, change)
                    previous_yaw = yaw
            finally:
                self.velocity_publisher.publish(Twist())
            if self.canceled(goal_handle):
                return None

            stopped_at = time.monotonic()
            frame = self.wait_for_new_frame(stopped_at, goal_handle)
            if frame is None:
                return None
            goal_handle.publish_feedback(
                ApproachObject.Feedback(status='Searching for object'))
            grounding = self.ask_vlm(object_name, frame)
            if self.canceled(goal_handle):
                return None
            if grounding.get('found'):
                return grounding, frame

            # Include any residual rotation that occurred while the robot stopped.
            yaw = self.current_yaw
            change = math.atan2(
                math.sin(yaw - previous_yaw),
                math.cos(yaw - previous_yaw))
            rotation += max(0.0, change)
            previous_yaw = yaw
        return None

    def ask_vlm(self, object_name, frame):
        encoded_ok, encoded_frame = cv2.imencode('.jpg', frame)
        if not encoded_ok:
            raise ValueError('Could not encode camera frame')
        image_data = base64.b64encode(encoded_frame).decode('ascii')
        question = (
            f'Locate the {object_name} in the image. Answer ONLY with JSON: '
            '{"found":true/false, "bbox": [x1, y1, x2, y2]} '
            'in pixel coordinates. If not found, return false and an empty bbox.')
        response = self.client.chat.completions.create(
            model=self.vlm_model,
            messages=[{'role': 'user', 'content': [
                {'type': 'text', 'text': question},
                {'type': 'image_url', 'image_url': {
                    'url': f'data:image/jpeg;base64,{image_data}',
                    # 'detail': 'low'
                    }},
            ]}])
        answer = response.choices[0].message.content
        return json.loads(answer[answer.find('{'):answer.rfind('}') + 1])

    def publish_bbox(self, coordinates):
        x1, y1, x2, y2 = coordinates
        message = Detection2D()
        message.header.stamp = self.get_clock().now().to_msg()
        message.bbox.center.position.x = float((x1 + x2) / 2.0)
        message.bbox.center.position.y = float((y1 + y2) / 2.0)
        message.bbox.size_x = float(x2 - x1)
        message.bbox.size_y = float(y2 - y1)
        self.bbox_publisher.publish(message)

    def execute(self, goal_handle):
        result = ApproachObject.Result()
        object_name = goal_handle.request.object_name
        searched = False
        try:
            for _ in range(120):
                if self.stop_requested.is_set() or goal_handle.is_cancel_requested:
                    result.message = f'Approach to {object_name} was canceled.'
                    goal_handle.canceled()
                    return result
                frame = self.camera.frame
                distance = self.camera.front_distance
                if frame is None or distance is None:
                    Event().wait(0.2)
                    continue
                grounding = self.ask_vlm(object_name, frame)
                # A stop request may arrive while the remote VLM call is running.
                if self.stop_requested.is_set() or goal_handle.is_cancel_requested:
                    result.message = f'Approach to {object_name} was canceled.'
                    goal_handle.canceled()
                    return result
                if not grounding.get('found'):
                    self.filtered_cmd = Twist()
                    self.velocity_publisher.publish(Twist())
                    if searched:
                        break
                    searched = True
                    search_result = self.search_for_object(
                        object_name, goal_handle)
                    if self.canceled(goal_handle):
                        result.message = f'Approach to {object_name} was canceled.'
                        goal_handle.canceled()
                        return result
                    if search_result is None:
                        break
                    grounding, frame = search_result
                    distance = self.camera.front_distance
                    if distance is None:
                        continue
                coordinates = grounding.get('bbox', [])
                if len(coordinates) != 4:
                    raise ValueError('VLM returned an invalid bounding box')
                x1, y1, x2, y2 = map(float, coordinates)
                self.publish_bbox((x1, y1, x2, y2))
                width = frame.shape[1]
                error = ((x1 + x2) / 2.0 - width / 2.0) / (width / 2.0)
                if distance <= 2.0 and abs(error) < 0.25:
                    result.success = True
                    result.message = f'I am now next to the {object_name}.'
                    goal_handle.succeed()
                    return result
                command = Twist()
                command.angular.z = -0.25 * error
                command.linear.x = 0.5 if abs(error) < 0.25 else 0.0
                filtered_command = self.apply_low_pass_filter(command)
                self.velocity_publisher.publish(filtered_command)
                goal_handle.publish_feedback(
                    ApproachObject.Feedback(status='Approaching object'))
            result.message = f'Sorry, I could not find the {object_name}.'
            goal_handle.abort()
            return result
        except Exception as error:
            self.get_logger().error(f'Approach failed: {error}')
            result.message = f'Could not approach the {object_name}: {error}'
            goal_handle.abort()
            return result
        finally:
            self.filtered_cmd = Twist()
            self.velocity_publisher.publish(self.filtered_cmd)
            with self.goal_lock:
                self.busy = False


def main():
    rclpy.init()
    camera = Camera()
    server = ApproachObjectServer(camera)
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(camera)
    executor.add_node(server)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        server.destroy_node()
        camera.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
