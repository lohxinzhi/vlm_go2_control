import argparse
import math
import os

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Image
from geometry_msgs.msg import Twist

from nav2_simple_commander.robot_navigator import BasicNavigator
import rclpy
from rclpy.node import Node


from cv_bridge import CvBridge
from openai import OpenAI 
import cv2, base64
import yaml
import json

#OpenAI
client = OpenAI()
MODEL = "gpt-4o-mini"
# MODEL = "gpt-5-mini"

#Qwen-VL
# API_KEY = os.environ.get('QWEN_API_KEY')
# client = OpenAI(api_key=API_KEY, base_url='https://dashscope-intl.aliyuncs.com/compatible-mode/v1')
# MODEL = 'qwen3-vl-flash'


GROUND = ('Locate the {obj} in the image. Answer ONLY with JSON: '
          '{{"found":true/false, "bbox": [x1, y1, x2, y2]}} '
          'in pixel coordinates. If the object is not found, return false and an empty bbox.')

def ask_vlm(client, model, image_bgr, question):
    ok, buf = cv2.imencode('.jpg', image_bgr)
    b64 = base64.b64encode(buf).decode()
    resp = client.chat.completions.create(
        model=model,
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

class ObjectApproach(Node):
    def __init__(self):
        super().__init__('object_approach_node')
        self.bridge, self.frame = CvBridge(), None
        self.create_subscription(Image, '/rgb_image', self.image_cb, 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        # self.timer = self.create_timer(2.0, self.approach)
        
    def image_cb(self, msg):
        self.frame = self.bridge.imgmsg_to_cv2(msg, 'bgr8')


    def approach(self):
        print("approaching")
        for _ in range(120): # safety-bounded loop
            obj = 'green cube'
            ans = ask_vlm(client, MODEL, self.frame, GROUND.format(obj=obj))
            d = json.loads(ans[ans.find('{'): ans.rfind('}') + 1])
            if not d['found']:
                # spin_in_place(self.cmd_pub)      # search behaviour
                continue
            x1, y1, x2, y2 = d['bbox']
            temp = self.frame.copy()
            cv2.rectangle(temp,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),  # BGR color: green
                2              # line thickness
            )
            print(ans)
            cv2.imshow('frame', temp)
            cv2.waitKey(1)



            # h, w = self.frame.shape[:2]
            # err = ((x1 + x2) / 2 - w / 2) / (w / 2)  # -1 .. 1
            # box_h = (y2 - y1) / h
            # cmd = Twist()
            # if box_h > 0.55: # close enough -> stop
            #     self.cmd_pub.publish(Twist())
            #     return True
            # cmd.angular.z = -0.5 * err
            # cmd.linear.x = 0.12 if abs(err) < 0.25 else 0.0
            # self.cmd_pub.publish(cmd)
        self.cmd_pub.publish(Twist())
        return False
    
        



def main():


    rclpy.init()

    object_approach_node = ObjectApproach()
    rclpy.spin(object_approach_node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()
