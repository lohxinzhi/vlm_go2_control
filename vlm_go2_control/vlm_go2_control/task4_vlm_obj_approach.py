import argparse
import math
import os
from threading import Event

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from sensor_msgs.msg import Image, LaserScan
from geometry_msgs.msg import Twist
from std_msgs.msg import Float32
from vision_msgs.msg import Detection2D

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node


from cv_bridge import CvBridge
from openai import OpenAI 
import cv2, base64
import yaml
import json
import numpy as np


#Qwen-VL
# API_KEY = os.environ.get('QWEN_API_KEY')
# client = OpenAI(api_key=API_KEY, base_url='https://ws-9lbexwoqsefh78p8.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1')
# MODEL = 'qwen3.5-flash'

world_dir = get_package_share_directory('go2_house_world')
room_yaml_path = os.path.join(world_dir, 'params', 'bto_rooms.yaml')


def make_pose(node: Node, x: float, y: float,
              yaw_deg: float) -> PoseStamped:
    """Create a PoseStamped message for navigation."""
    p = PoseStamped()
    p.header.frame_id = 'map'
    p.header.stamp = node.get_clock().now().to_msg()
    p.pose.position.x = x
    p.pose.position.y = y
    yaw_rad = math.radians(yaw_deg)
    p.pose.orientation.z = math.sin(yaw_rad / 2)
    p.pose.orientation.w = math.cos(yaw_rad / 2)
    return p

class Camera (Node):
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

    
class VLMDialogue(Node):
    def __init__(self, cam:Camera):
        super().__init__('vlm_agent')
        with open(room_yaml_path, 'r', encoding='utf-8') as room_file:
            self.rooms = yaml.safe_load(room_file)['rooms']
        room_names = ', '.join(room['name'] for room in self.rooms.values())
        self.SYSTEM = '''You are the dialogue manager of an indoor assistant robot.
            For EVERY user message, reply ONLY with one JSON object, no other text:
            {"actions": [{"action": "approach", "object": "<object name>"}]}
            The actions array must be nonempty and may contain multiple actions in
            the order they should be performed. Each action must be one of:
            {"action": "goto_room", "room": <int 0-4>}
            {"action": "goto_room_name", "room_name": "<room name>"}
            {"action": "approach", "object": "<object name>"}
            {"action": "stop"}
            {"action": "chat", "reply": "<answer or clarification question>"}
            Use a separate approach action for each requested object. A stop action
            ends the sequence. If the request is impossible or unsafe, use a chat
            action to explain instead of planning that action.
            Use goto_room for a room ID and goto_room_name for a room name.
            Valid room names are: ''' + room_names + '.'
        self.history = [{'role': 'system', 'content': self.SYSTEM}]
        self.ground = ('Locate the {obj} in the image. Answer ONLY with JSON: '
          '{{"found":true/false, "bbox": [x1, y1, x2, y2]}} '
          'in pixel coordinates. If the object is not found, return false and an empty bbox.')
        self.cam = cam
        
        self.client = OpenAI()
        self.text_model = 'gpt-5-mini'    # any chat model, e.g. 'gpt-5-mini' (OpenAI) or 'qwen-plus' (Alibaba)
        # self.vlm_model = "gpt-4o-mini"
        self.vlm_model = "gpt-5.6-luna"

        self.timer = self.create_timer(0.2,self.timer_cb)
        self.pub_cmd = self.create_publisher(Twist, "/cmd_vel", 10)
        self.pub_bbox = self.create_publisher(Detection2D, "/ground_bbox", 10)
        self.nav_callback_group = ReentrantCallbackGroup()
        self.nav_client = ActionClient(
            self, NavigateToPose, '/navigate_to_pose',
            callback_group=self.nav_callback_group)

    def room_id_from_name(self, room_name: str):
        """Resolve a room name from the YAML file, ignoring case and spacing."""
        normalized_name = ' '.join(room_name.split()).casefold()
        for room_id, room in self.rooms.items():
            if ' '.join(room['name'].split()).casefold() == normalized_name:
                return room_id
        return None

    def goto_room(self, room_id: int) -> str:
        """Send a room pose to bt_navigator and wait for its result."""
        if room_id not in self.rooms:
            raise KeyError(f'Room {room_id} is not defined in bto_rooms.yaml')
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            return 'UNAVAILABLE'

        room = self.rooms[room_id]
        goal = NavigateToPose.Goal()
        goal.pose = make_pose(self, room['x'], room['y'], room['yaw_deg'])
        goal_future = self.nav_client.send_goal_async(goal)
        goal_ready = Event()
        goal_future.add_done_callback(lambda _: goal_ready.set())
        while rclpy.ok() and not goal_ready.wait(0.2):
            pass
        if not goal_ready.is_set():
            return 'FAILED'

        goal_handle = goal_future.result()
        if not goal_handle.accepted:
            return 'REJECTED'

        result_future = goal_handle.get_result_async()
        result_ready = Event()
        result_future.add_done_callback(lambda _: result_ready.set())
        while rclpy.ok() and not result_ready.wait(0.2):
            pass
        if not result_ready.is_set():
            return 'FAILED'

        status = result_future.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            return 'SUCCEEDED'
        if status == GoalStatus.STATUS_CANCELED:
            return 'CANCELED'
        return 'FAILED'
    
    def timer_cb(self):
        user = input('You: ').strip()
        self.history.append({'role': 'user', 'content': user})
        out = self.client.chat.completions.create(model=self.text_model, messages=self.history)
        plan = json.loads(out.choices[0].message.content)
        self.history.append({'role': 'assistant', 'content': json.dumps(plan)})
        replies = []
        for cmd in plan['actions']:
            if cmd['action'] in ('goto_room', 'goto_room_name'):
                if cmd['action'] == 'goto_room_name':
                    room_id = self.room_id_from_name(cmd['room_name'])
                    if room_id is None:
                        replies.append(f"Room {cmd['room_name']} is not defined.")
                        break
                else:
                    room_id = cmd['room']
                if room_id not in self.rooms:
                    replies.append(f'Room {room_id} is not defined.')
                    break
                result = self.goto_room(room_id)
                room_name = self.rooms[room_id]['name']
                if result == 'SUCCEEDED':
                    replies.append(f'Arrived at {room_name}.')
                else:
                    replies.append(f'Could not reach {room_name}: {result}.')
                    break
            elif cmd['action'] == 'approach':
                ok = self.approach(cmd['object'])
                replies.append(
                    f"I am now next to the {cmd['object']}." if ok else
                    f"Sorry, I could not find the {cmd['object']}.")
                if not ok:
                    break
            elif cmd['action'] == 'stop':
                self.pub_cmd.publish(Twist())
                replies.append('Stopped.')
                break
            elif cmd['action'] == 'chat':
                replies.append(cmd['reply'])
        reply = ' '.join(replies)
        print('Robot:', reply)
        self.history.append({'role': 'assistant', 'content': reply})

    def ask_vlm(self, question):
        ok, buf = cv2.imencode('.jpg', self.cam.frame)
        b64 = base64.b64encode(buf).decode()
        resp = self.client.chat.completions.create(
            model=self.vlm_model,
            messages=[{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': question},
                    {'type': 'image_url', 'image_url': 
                        {'url': f'data:image/jpeg;base64,{b64}',
                        'details': 'low'
                        }},
                ]
            }]
        )
        return resp.choices[0].message.content

    def approach(self, obj):
        for _ in range(120): # safety-bounded loop
            ans = self.ask_vlm(self.ground.format(obj=obj))
            d = json.loads(ans[ans.find('{'): ans.rfind('}') + 1])
            cmd = Twist()
            if not d['found']:
                # spin_in_place(pub)        # search behaviour
                # cmd.angular.z = np.float64(1.0)
                continue
            x1, y1, x2, y2 = d['bbox']
            bbox_msg = self.get_bbox_msg(x1,y1,x2,y2)
            self.pub_bbox.publish(bbox_msg) # publish bbox

            h, w = self.cam.frame.shape[:2]
            err = ((x1 + x2) / 2 - w / 2) / (w / 2)
            # -1 .. 1
            # box_h = (y2 - y1) / h
            # if box_h > 0.55:        # close enough -> stop
            if self.cam.front_distance <= 2.0 and err < 0.25:        # close enough -> stop
                self.pub_cmd.publish(cmd)
                return True
            cmd.angular.z = -0.1 * err
            cmd.linear.x = 0.5 if abs(err) < 0.25 else 0.0
            self.pub_cmd.publish(cmd)
        self.pub_cmd.publish(Twist())
        return False

    def get_bbox_msg(self, x1,y1,x2,y2):
        bbox_msg = Detection2D()
        bbox_msg.header.stamp = self.get_clock().now().to_msg()
        bbox_msg.bbox.center.position.x = np.float64((x1 + x2) / 2.0)
        bbox_msg.bbox.center.position.y = np.float64((y1 + y2) / 2.0)
        bbox_msg.bbox.size_x = np.float64(x2 - x1)
        bbox_msg.bbox.size_y = np.float64(y2 - y1)
        return bbox_msg

    


def main():


    rclpy.init()
    cam = Camera()
    vlm_manager = VLMDialogue(cam)

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(cam)
    executor.add_node(vlm_manager)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        cam.destroy_node()
        vlm_manager.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
