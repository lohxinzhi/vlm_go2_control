"""Describe the robot's current camera view through a ROS service."""

import base64
import time

import cv2
from cv_bridge import CvBridge
from openai import OpenAI
from sensor_msgs.msg import Image

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from vlm_go2_interfaces.srv import DescribeScene


SCENE_DESCRIPTION_PROMPT = (
    'You are the visual perception system of an indoor mobile robot. '
    'Describe only what is clearly visible in the supplied image. '
    'Pay particular attention to coloured geometric objects. '
    'State their colour and shape when confident. '
    'Keep the description concise and factual. '
    'Do not guess objects that are hidden or not visually supported.'
)


class DescribeSceneServer(Node):
    """Buffer the latest image and describe it when a client requests it."""

    def __init__(self):
        super().__init__('describe_scene_server')
        self.bridge = CvBridge()
        self.frame = None
        self.frame_received_at = None
        self.vlm_model = self.declare_parameter(
            'vlm_model', 'gpt-5.6-luna').value
        self.stale_frame_threshold_sec = self.declare_parameter(
            'stale_frame_threshold_sec', 2.0).value
        self.client = OpenAI(timeout=30.0)
        group = ReentrantCallbackGroup()
        self.create_subscription(
            Image, '/rgb_image', self.on_image, qos_profile_sensor_data,
            callback_group=group)
        self.service = self.create_service(
            DescribeScene, '/describe_scene', self.describe,
            callback_group=group)

    def on_image(self, message):
        try:
            self.frame = self.bridge.imgmsg_to_cv2(
                message, desired_encoding='bgr8')
            self.frame_received_at = time.monotonic()
        except Exception as error:
            self.get_logger().warning(f'Rejected camera frame: {error}')

    def describe(self, _request, response):
        frame = self.frame
        received_at = self.frame_received_at
        if frame is None or received_at is None:
            response.message = 'No camera frame is available.'
            return response
        if time.monotonic() - received_at > self.stale_frame_threshold_sec:
            response.message = 'The latest camera frame is stale.'
            return response

        try:
            encoded_ok, encoded_frame = cv2.imencode('.jpg', frame)
            if not encoded_ok:
                raise ValueError('Could not encode camera frame')
            image_data = base64.b64encode(encoded_frame).decode('ascii')
            result = self.client.chat.completions.create(
                model=self.vlm_model,
                messages=[{'role': 'user', 'content': [
                    {'type': 'text', 'text': SCENE_DESCRIPTION_PROMPT},
                    {'type': 'image_url', 'image_url': {
                        'url': f'data:image/jpeg;base64,{image_data}',
                        'detail': 'low'}},
                ]}])
            description = result.choices[0].message.content
            if not description or not description.strip():
                raise ValueError('VLM returned an empty description')
            response.description = description.strip()
            response.success = True
        except Exception as error:
            self.get_logger().error(f'Scene description failed: {error}')
            response.message = f'Could not describe the scene: {error}'
        return response


def main():
    rclpy.init()
    server = DescribeSceneServer()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(server)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        server.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
