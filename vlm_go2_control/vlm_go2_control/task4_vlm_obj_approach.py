import argparse
import math
import os

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Image, LaserScan
from geometry_msgs.msg import Twist
from vision_msgs.msg import Detection2D

from nav2_simple_commander.robot_navigator import BasicNavigator
import rclpy
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




def make_pose(nav: BasicNavigator, x: float, y: float,
              yaw_deg: float) -> PoseStamped:
    """Create a PoseStamped message for navigation."""
    p = PoseStamped()
    p.header.frame_id = 'map'
    p.header.stamp = nav.get_clock().now().to_msg()
    p.pose.position.x = x
    p.pose.position.y = y
    yaw_rad = math.radians(yaw_deg)
    p.pose.orientation.z = math.sin(yaw_rad / 2)
    p.pose.orientation.w = math.cos(yaw_rad / 2)
    return p


def goto_room(room_id: int, nav: BasicNavigator, rooms: dict) -> str:
    """Navigate to the room identified by room_id."""
    if room_id not in rooms:
        raise KeyError(f'Room {room_id} is not defined in bto_rooms.yaml')

    room = rooms[room_id]
    nav.goToPose(make_pose(
        nav, room['x'], room['y'], room['yaw_deg']))
    while not nav.isTaskComplete():
        rclpy.spin_once(nav, timeout_sec=0.2)
    return str(nav.getResult())  # SUCCEEDED / CANCELED / FAILED

class Camera (Node):
    def __init__(self):
        super().__init__('cam_buffer')
        self.frame = None
        self.scan = None
        self.front_distance = None
        self.bridge = CvBridge()
        self.create_subscription(Image, '/rgb_image', self.cam_cb, 10)
        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)

    def cam_cb(self, msg):
        self.frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

    def scan_cb(self, msg):
        self.scan = msg
        self.front_distance = self.get_front_distance(msg)
        print(self.front_distance)

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
        self.SYSTEM = '''You are the dialogue manager of an indoor assistant robot.
            For EVERY user message, reply ONLY with
            one JSON object, no other text:
            {"action": "approach", "object": "<object name>"}
            {"action": "stop"}
            {"action": "chat", "reply": "<answer or clarification question>"}
            If the request is impossible (unknown room, unsafe), use "chat" to explain.'''
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
    
    def timer_cb(self):
        user = input('You: ').strip()
        self.history.append({'role': 'user', 'content': user})
        out = self.client.chat.completions.create(model=self.text_model, messages=self.history)
        cmd = json.loads(out.choices[0].message.content)
        self.history.append({'role': 'assistant', 'content': json.dumps(cmd)})
        # if cmd['action'] == 'goto_room':
        #     result = goto_room(cmd['room'])
        #     reply = report_arrival(result, cmd['room'])
        # + auto describe
        # elif cmd['action'] == 'describe':
        #     reply = describe_scene()
        if cmd['action'] == 'approach':
            ok = self.approach(cmd['object'])
            reply = f"I am now next to the {cmd['object']}." if ok else \
            f"Sorry, I could not find the {cmd['object']}."
        else:
            reply = cmd.get('reply', 'Stopped.')
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
            bbox_msg = Detection2D()
            bbox_msg.header.stamp = self.get_clock().now().to_msg()
            bbox_msg.bbox.center.position.x = np.float64((x1 + x2) / 2.0)
            bbox_msg.bbox.center.position.y = np.float64((y1 + y2) / 2.0)
            bbox_msg.bbox.size_x = np.float64(x2 - x1)
            bbox_msg.bbox.size_y = np.float64(y2 - y1)
            self.pub_bbox.publish(bbox_msg)

            h, w = self.cam.frame.shape[:2]
            err = ((x1 + x2) / 2 - w / 2) / (w / 2)
            # -1 .. 1
            box_h = (y2 - y1) / h
            if box_h > 0.55:        # close enough -> stop
                self.pub_cmd.publish(cmd)
                return True
            cmd.angular.z = -0.1 * err
            cmd.linear.x = 0.5 if abs(err) < 0.25 else 0.0
            self.pub_cmd.publish(cmd)
        self.pub_cmd.publish(Twist())
        return False
    


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
