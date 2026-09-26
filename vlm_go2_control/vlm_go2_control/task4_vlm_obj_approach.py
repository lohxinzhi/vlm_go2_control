"""Camera buffer and JSON dialogue manager for the Go2 task actions."""

import json
import math
import os
import sys
from threading import Event, Lock

from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from openai import OpenAI
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Float32, String
from std_srvs.srv import Trigger
import yaml

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from vlm_go2_interfaces.action import ApproachObject, GoToRoom
from vlm_go2_interfaces.srv import DescribeScene


class Camera(Node):
    """Buffer camera and front laser readings for the approach action server."""

    def __init__(self):
        super().__init__('cam_buffer')
        self.frame = None
        self.scan = None
        self.front_distance = None
        self.bridge = CvBridge()
        self.create_subscription(Image, '/rgb_image', self.cam_cb, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)
        self.front_distance_publisher = self.create_publisher(
            Float32, '/front_distance', 10)

    def cam_cb(self, msg):
        self.frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

    def scan_cb(self, msg):
        self.scan = msg
        self.front_distance = self.get_front_distance(msg)
        if self.front_distance is not None:
            distance_msg = Float32()
            distance_msg.data = self.front_distance
            self.front_distance_publisher.publish(distance_msg)

    @staticmethod
    def get_front_distance(scan):
        """Return the nearest valid laser range closest to the front axis."""
        valid_ranges = (
            (abs(scan.angle_min + index * scan.angle_increment), distance)
            for index, distance in enumerate(scan.ranges)
            if math.isfinite(distance)
            and scan.range_min <= distance <= scan.range_max
        )
        nearest_beam = min(valid_ranges, default=None)
        return nearest_beam[1] if nearest_beam is not None else None


def wait_for_future(future):
    """Wait while the multithreaded executor processes action callbacks."""
    ready = Event()
    future.add_done_callback(lambda _: ready.set())
    while rclpy.ok() and not ready.wait(0.2):
        pass
    return future.result() if ready.is_set() else None


class VLMDialogue(Node):
    """Turn requests into JSON actions and relay them to ROS action servers."""

    def __init__(self):
        super().__init__('vlm_agent')
        room_path = os.path.join(
            get_package_share_directory('go2_house_world'),
            'params', 'bto_rooms.yaml')
        with open(room_path, 'r', encoding='utf-8') as room_file:
            self.rooms = yaml.safe_load(room_file)['rooms']
        room_names = ', '.join(room['name'] for room in self.rooms.values())
        room_ids = ', '.join(str(room_id) for room_id in self.rooms)
        system = (
            'You are the dialogue manager of an indoor Unitree Go2 robot. '
            'Convert each user request into exactly one JSON object, no other text. '
            '{"actions": [{"action": "approach", "object": "<object name>"}]} '
            'The actions array must be nonempty and may contain multiple actions '
            'in order. Allowed actions: '
            '{"action": "goto_room", "room": <integer>}, '
            '{"action": "goto_room_name", "room_name": "<room name>"}, '
            '{"action": "describe"}, '
            '{"action": "approach", "object": "<object name>"}, '
            '{"action": "stop"}, '
            '{"action": "chat", "reply": "<answer or clarification>"}. '
            'Use a separate approach action for each object. Stop ends the sequence. '
            'For an impossible or unsafe request, use chat to explain. '
            f'Valid room names: {room_names}. Valid room ids: {room_ids}.')
        self.history = [{'role': 'system', 'content': system}]
        self.client = OpenAI()
        self.text_model = 'gpt-5-mini'
        group = ReentrantCallbackGroup()
        self.room_client = ActionClient(
            self, GoToRoom, '/go_to_room', callback_group=group)
        self.approach_client = ActionClient(
            self, ApproachObject, '/approach_object', callback_group=group)
        self.stop_client = self.create_client(
            Trigger, '/stop_approach', callback_group=group)
        self.describe_client = self.create_client(
            DescribeScene, '/describe_scene', callback_group=group)
        self.actions_publisher = self.create_publisher(String, '/vlm/actions', 10)
        self.request_lock = Lock()
        self.create_subscription(
            String, '/vlm/user_request', self.request_cb, 10,
            callback_group=group)
        use_console = self.declare_parameter(
            'use_console_input', sys.stdin.isatty()).value
        if use_console:
            self.create_timer(0.2, self.timer_cb)

    def room_id_from_name(self, room_name):
        normalized = ' '.join(room_name.split()).casefold()
        for room_id, room in self.rooms.items():
            if ' '.join(room['name'].split()).casefold() == normalized:
                return int(room_id)
        return None

    def send_action(self, client, goal):
        if not client.wait_for_server(timeout_sec=5.0):
            return False, 'Action server unavailable.'
        goal_handle = wait_for_future(client.send_goal_async(goal))
        if goal_handle is None or not goal_handle.accepted:
            return False, 'Action goal rejected.'
        result = wait_for_future(goal_handle.get_result_async())
        if result is None:
            return False, 'Action did not return a result.'
        return result.result.success, result.result.message

    def execute_command(self, command):
        action = command.get('action')
        if action in ('goto_room', 'goto_room_name'):
            if action == 'goto_room_name':
                room_name = command.get('room_name', '')
                room_id = self.room_id_from_name(room_name)
                if room_id is None:
                    return f'Room {room_name} is not defined.', False
            else:
                room_id = command.get('room')
            if room_id not in self.rooms:
                return f'Room {room_id} is not defined.', False
            goal = GoToRoom.Goal()
            goal.room_id = int(room_id)
            print(f"Robot: Going to {self.rooms[room_id]['name']}.", flush=True)
            success, message = self.send_action(self.room_client, goal)
            return message, success
        if action == 'approach':
            object_name = command.get('object', '')
            if not isinstance(object_name, str) or not object_name.strip():
                return 'Invalid object name.', False
            goal = ApproachObject.Goal()
            goal.object_name = object_name
            print(f'Robot: Approaching the {object_name}.', flush=True)
            success, message = self.send_action(self.approach_client, goal)
            return message, success
        if action == 'describe':
            if not self.describe_client.wait_for_service(timeout_sec=5.0):
                return 'Scene description service unavailable.', False
            response = wait_for_future(
                self.describe_client.call_async(DescribeScene.Request()))
            if response is None:
                return 'Scene description did not return a response.', False
            return (response.description if response.success else response.message,
                    response.success)
        if action == 'stop':
            if not self.stop_client.wait_for_service(timeout_sec=5.0):
                return 'Stop service unavailable.', False
            response = wait_for_future(self.stop_client.call_async(Trigger.Request()))
            return (response.message, response.success) if response else ('Stop failed.', False)
        if action == 'chat':
            return str(command.get('reply', '')), True
        return 'Invalid command.', False

    def timer_cb(self):
        try:
            self.process_request(input('You: ').strip())
        except EOFError:
            pass

    def request_cb(self, message):
        self.process_request(message.data.strip())

    def process_request(self, user):
        if not user:
            return
        # Keep dialogue history and action sequences in request order.
        with self.request_lock:
            self.run_request(user)

    def run_request(self, user):
        self.history.append({'role': 'user', 'content': user})
        try:
            output = self.client.chat.completions.create(
                model=self.text_model, messages=self.history)
            plan = json.loads(output.choices[0].message.content)
            if not isinstance(plan, dict) or not isinstance(plan.get('actions'), list):
                raise ValueError('Expected an actions array')
            message = String()
            message.data = json.dumps(plan)
            self.actions_publisher.publish(message)
            self.history.append({'role': 'assistant', 'content': message.data})
            replies = []
            for command in plan['actions']:
                if not isinstance(command, dict):
                    replies.append('Invalid command.')
                    break
                reply, success = self.execute_command(command)
                replies.append(reply)
                if not success or command.get('action') == 'stop':
                    break
            reply = ' '.join(replies)
        except (ValueError, KeyError, TypeError) as error:
            reply = f'Could not interpret the action plan: {error}'
        except Exception as error:
            self.get_logger().error(f'Dialogue failed: {error}')
            reply = 'Sorry, I could not complete that request.'
        print('Robot:', reply, flush=True)
        self.history.append({'role': 'assistant', 'content': reply})


def main():
    rclpy.init()
    dialogue = VLMDialogue()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(dialogue)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        dialogue.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
