"""Camera buffer and JSON dialogue manager for the Go2 task actions."""

import json
import math
import os
import sys
import time
from queue import Queue
from threading import Event, Lock, Thread

from ament_index_python.packages import get_package_share_directory
from cv_bridge import CvBridge
from openai import OpenAI
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import Float32, String
from std_srvs.srv import SetBool, Trigger
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
        self.frame_received_at = None
        self.scan = None
        self.front_distance = None
        self.bridge = CvBridge()
        self.create_subscription(Image, '/rgb_image', self.cam_cb, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)
        self.front_distance_publisher = self.create_publisher(
            Float32, '/front_distance', 10)

    def cam_cb(self, msg):
        self.frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')
        self.frame_received_at = time.monotonic()

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


class VLMDialogueManager(Node):
    """Turn requests into JSON actions and relay them to ROS action servers."""

    def __init__(self):
        super().__init__('vlm_dialogue_manager')
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
            '{"action": "describe", "mode": "describe"}, '
            '{"action": "describe", "mode": "vqa", '
            '"question": "<specific question about the current view>"}, '
            '{"action": "approach", "object": "<object name>"}, '
            '{"action": "stop"}, '
            '{"action": "chat", "reply": "<answer or clarification>"}. '
            'Use describe mode for a general account of the current view. '
            'Use vqa mode for a specific question about what the robot can see; '
            'preserve the question in the question field. Do not answer visual '
            'questions from memory with chat. '
            'Use a separate approach action for each object. Stop ends the sequence. '
            'For an impossible or unsafe request, use chat to explain. '
            f'Valid room names: {room_names}. Valid room ids: {room_ids}.')
        self.history = [{'role': 'system', 'content': system}]
        client_type = self.declare_parameter(
            'client_type', 'openai').value.lower()
        if client_type == 'openai':
            self.client = OpenAI()
            default_model = 'gpt-5-mini'
        elif client_type == 'qwen':
            self.client = OpenAI(
                api_key=os.environ.get('QWEN_API_KEY'),
                base_url=os.environ.get('QWEN_BASE_URL'))
            default_model = 'qwen3.5-flash'
        else:
            raise ValueError(f'Unsupported client type: {client_type}')
        self.text_model = self.declare_parameter('model', default_model).value
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
        self.reply_publisher = self.create_publisher(String, '/vlm/reply', 10)
        self.request_queue = Queue()
        self.history_lock = Lock()
        self.motion_lock = Lock()
        self.plan_lock = Lock()
        self.active_plan = None
        self.active_goal = None
        self.manual_control = False
        self.create_service(
            SetBool, '/vlm/manual_control', self.set_manual_control,
            callback_group=group)
        Thread(target=self.request_worker, daemon=True).start()
        self.create_subscription(
            String, '/vlm/user_request', self.request_cb, 10,
            callback_group=group)
        use_console = self.declare_parameter(
            'use_console_input', sys.stdin.isatty()).value
        if use_console:
            Thread(target=self.console_worker, daemon=True).start()

    def room_id_from_name(self, room_name):
        normalized = ' '.join(room_name.split()).casefold()
        for room_id, room in self.rooms.items():
            if ' '.join(room['name'].split()).casefold() == normalized:
                return int(room_id)
        return None

    def send_action(self, client, goal, cancel_event=None):
        if not client.wait_for_server(timeout_sec=5.0):
            return False, 'Action server unavailable.'
        if cancel_event is not None and cancel_event.is_set():
            return False, 'Action canceled.'
        goal_handle = wait_for_future(client.send_goal_async(goal))
        if goal_handle is None or not goal_handle.accepted:
            return False, 'Action goal rejected.'
        with self.plan_lock:
            self.active_goal = goal_handle
        result_future = goal_handle.get_result_async()
        cancellation_sent = False
        while rclpy.ok() and not result_future.done():
            if (cancel_event is not None and cancel_event.is_set()
                    and not cancellation_sent):
                goal_handle.cancel_goal_async()
                cancellation_sent = True
            Event().wait(0.1)
        with self.plan_lock:
            if self.active_goal is goal_handle:
                self.active_goal = None
        result = result_future.result() if result_future.done() else None
        if result is None:
            return False, 'Action did not return a result.'
        return result.result.success, result.result.message

    def execute_command(self, command, cancel_event=None):
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
            success, message = self.send_action(self.room_client, goal, cancel_event)
            return message, success
        if action == 'approach':
            object_name = command.get('object', '')
            if not isinstance(object_name, str) or not object_name.strip():
                return 'Invalid object name.', False
            goal = ApproachObject.Goal()
            goal.object_name = object_name
            print(f'Robot: Approaching the {object_name}.', flush=True)
            success, message = self.send_action(self.approach_client, goal, cancel_event)
            return message, success
        if action == 'describe':
            question = command.get('question', '')
            mode = command.get('mode', 'vqa' if question else 'describe')
            if mode not in ('describe', 'vqa'):
                return 'Invalid scene request mode.', False
            if mode == 'vqa' and (
                    not isinstance(question, str) or not question.strip()):
                return 'A visual question is required for vqa mode.', False
            if not self.describe_client.wait_for_service(timeout_sec=5.0):
                return 'Scene description service unavailable.', False
            request = DescribeScene.Request()
            request.mode = mode
            request.question = question.strip() if mode == 'vqa' else ''
            response = wait_for_future(
                self.describe_client.call_async(request))
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

    def console_worker(self):
        while rclpy.ok():
            try:
                self.process_request(input('You: ').strip())
            except EOFError:
                return

    def request_cb(self, message):
        self.process_request(message.data.strip())

    def process_request(self, user):
        if user:
            self.request_queue.put(user)

    def request_worker(self):
        while rclpy.ok():
            user = self.request_queue.get()
            self.run_request(user)

    def validate_command(self, command):
        if not isinstance(command, dict):
            return False
        action = command.get('action')
        if action == 'goto_room':
            return isinstance(command.get('room'), int) and command['room'] in self.rooms
        if action == 'goto_room_name':
            name = command.get('room_name')
            return isinstance(name, str) and self.room_id_from_name(name) is not None
        if action == 'approach':
            return isinstance(command.get('object'), str) and bool(command['object'].strip())
        if action == 'describe':
            question = command.get('question', '')
            mode = command.get('mode', 'vqa' if question else 'describe')
            return mode == 'describe' or (
                mode == 'vqa' and isinstance(question, str) and
                bool(question.strip()))
        return action in ('stop', 'chat')

    def report_reply(self, reply):
        print('Robot:', reply, flush=True)
        self.reply_publisher.publish(String(data=reply))
        with self.history_lock:
            self.history.append({'role': 'assistant', 'content': reply})

    def set_manual_control(self, request, response):
        """Cancel and drain autonomous motion before granting GUI control."""
        with self.plan_lock:
            self.manual_control = request.data
            if request.data and self.active_plan is not None:
                self.active_plan.set()
        if request.data:
            if not self.motion_lock.acquire(timeout=8.0):
                response.message = 'Motion is still stopping; try enabling control again.'
                return response
            self.motion_lock.release()
        response.success = True
        response.message = (
            'Manual control enabled.' if request.data else 'Manual control released.')
        return response

    def execute_plan(self, commands, cancel_event):
        # Wait for the previous action server to finish cancellation before
        # sending another motion goal to either server.
        with self.motion_lock:
            replies = []
            for command in commands:
                if cancel_event.is_set():
                    break
                reply, success = self.execute_command(command, cancel_event)
                replies.append(reply)
                if not success or command['action'] == 'stop':
                    break
            if not cancel_event.is_set() and replies:
                self.report_reply(' '.join(replies))

    def execute_non_motion(self, commands):
        replies = []
        for command in commands:
            reply, success = self.execute_command(command)
            replies.append(reply)
            if not success or command['action'] == 'stop':
                break
        self.report_reply(' '.join(replies))

    def run_request(self, user):
        with self.history_lock:
            self.history.append({'role': 'user', 'content': user})
            messages = list(self.history)
        try:
            output = self.client.chat.completions.create(
                model=self.text_model, messages=messages)
            plan = json.loads(output.choices[0].message.content)
            if (not isinstance(plan, dict) or
                    not isinstance(plan.get('actions'), list) or
                    not plan['actions']):
                raise ValueError('Expected an actions array')
            if not all(self.validate_command(command) for command in plan['actions']):
                raise ValueError('Invalid command in action plan')
            message = String()
            message.data = json.dumps(plan)
            self.actions_publisher.publish(message)
            with self.history_lock:
                self.history.append({'role': 'assistant', 'content': message.data})
            commands = plan['actions']
            changes_motion = any(command['action'] in
                                 ('goto_room', 'goto_room_name', 'approach', 'stop')
                                 for command in commands)
            if changes_motion:
                with self.plan_lock:
                    if self.manual_control:
                        self.report_reply('Release manual control in the dashboard first.')
                        return
                    if self.active_plan is not None:
                        self.active_plan.set()
                    cancel_event = Event()
                    self.active_plan = cancel_event
                Thread(target=self.execute_plan, args=(commands, cancel_event),
                       daemon=True).start()
            else:
                Thread(target=self.execute_non_motion, args=(commands,),
                       daemon=True).start()
            return
        except (ValueError, KeyError, TypeError) as error:
            reply = f'Could not interpret the action plan: {error}'
        except Exception as error:
            self.get_logger().error(f'Dialogue failed: {error}')
            reply = 'Sorry, I could not complete that request.'
        self.report_reply(reply)


def main():
    rclpy.init()
    dialogue = VLMDialogueManager()
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
