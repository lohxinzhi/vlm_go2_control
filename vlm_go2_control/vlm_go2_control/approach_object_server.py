"""Ground an object in camera frames and approach it through an action."""

import base64
import json
from threading import Event, Lock

import cv2
from geometry_msgs.msg import Twist
from openai import OpenAI
from std_srvs.srv import Trigger
from vision_msgs.msg import Detection2D

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from vlm_go2_interfaces.action import ApproachObject

from vlm_go2_control.vlm_dialogue_manager import Camera


class ApproachObjectServer(Node):
    """Run the bounded camera guided approach loop and return its result."""

    def __init__(self, camera):
        super().__init__('approach_object_server')
        self.camera = camera
        self.client = OpenAI()
        self.vlm_model = 'gpt-5.6-luna'
        self.stop_requested = Event()
        self.goal_lock = Lock()
        self.busy = False
        self.filter_alpha = 0.25
        self.filtered_cmd = Twist()
        self.velocity_publisher = self.create_publisher(Twist, '/cmd_vel', 10)
        self.bbox_publisher = self.create_publisher(
            Detection2D, '/ground_bbox', 10)
        group = ReentrantCallbackGroup()
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
                    'detail': 'low'}},
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
                    self.velocity_publisher.publish(Twist())
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
                command.angular.z = -0.1 * error
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
