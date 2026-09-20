"""Synthetic integration; publishes only to a unique test image topic."""
import time
import uuid
import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data
from go2_vlm_interfaces.srv import CaptureScene, QueryScene
from sensor_msgs.msg import Image
from go2_vlm_scene.scene_server import SceneServer


def test_ros_services(tmp_path):
    topic = '/go2_vlm_test/image_' + uuid.uuid4().hex
    rclpy.init(args=['--ros-args', '-p', f'camera_topic:={topic}',
                    '-p', f'runtime_data_directory:={tmp_path}',
                    '-p', 'stale_frame_threshold_sec:=0.5'])
    server = SceneServer()
    node = rclpy.create_node('scene_test_client')
    executor = SingleThreadedExecutor()
    executor.add_node(server)
    executor.add_node(node)

    def call(client, request):
        assert client.wait_for_service(timeout_sec=5)
        future = client.call_async(request)
        executor.spin_until_future_complete(future, timeout_sec=5)
        assert future.done()
        return future.result()

    try:
        capture = node.create_client(CaptureScene, '/go2_vlm/capture_scene')
        query = node.create_client(QueryScene, '/go2_vlm/query')
        response = call(capture, CaptureScene.Request())
        assert not response.success and 'NO_FRAME' in response.error_message
        publisher = node.create_publisher(Image, topic, qos_profile_sensor_data)
        deadline = time.monotonic() + 5
        while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        assert publisher.get_subscription_count() == 1
        bgr = np.zeros((480, 640, 3), dtype=np.uint8)
        bgr[:, :, 2] = 255
        message = CvBridge().cv2_to_imgmsg(bgr, encoding='bgr8')
        message.header.stamp.sec = 123
        message.header.stamp.nanosec = 456
        message.header.frame_id = 'synthetic_camera'
        deadline = time.monotonic() + 5
        while server._first_frame and time.monotonic() < deadline:
            publisher.publish(message)
            executor.spin_once(timeout_sec=0.05)
        assert not server._first_frame
        response = call(capture, CaptureScene.Request(save_image=True))
        assert response.success, response.error_message
        assert response.image_stamp.sec == 123 and response.image_stamp.nanosec == 456
        assert response.frame_id == 'synthetic_camera'
        saved = cv2.imread(response.saved_path)
        assert saved.shape == (480, 640, 3) and tuple(saved[0, 0]) == (0, 0, 255)
        result = call(query, QueryScene.Request(mode='describe', scene_id=response.scene_id))
        assert not result.success and result.error_message.startswith('EXTERNAL_API_DISABLED')
        assert result.scene_id == response.scene_id
        assert not result.answer and result.model == 'gpt-4o-mini' and not result.usage_json
        assert result.provider == 'openai'
        result = call(query, QueryScene.Request(mode='describe', provider='gemini', scene_id=response.scene_id))
        assert result.error_message.startswith('EXTERNAL_API_DISABLED')
        assert result.provider == 'gemini' and result.model == 'gemini-3.8-flash'
        assert result.scene_id == response.scene_id
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        result = call(capture, CaptureScene.Request())
        assert not result.success and 'STALE_FRAME' in result.error_message
        result = call(query, QueryScene.Request(scene_id=response.scene_id))
        assert result.scene_id == response.scene_id
        assert not any(name == '/cmd_vel' for name, _ in
                       node.get_publisher_names_and_types_by_node('scene_server', '/'))
    finally:
        executor.shutdown()
        server.destroy_node()
        node.destroy_node()
        rclpy.shutdown()
