import time
import json
from datetime import datetime, timezone

from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from go2_vlm_interfaces.srv import CaptureScene, QueryScene

from .camera import CameraBuffer, SceneError
from .image_storage import save_scene
from .providers.config import DEFAULT_MODELS
from .query_pipeline import query_scene
from .types import QueryOptions
from .query_log import QueryLog
from .prompts import PROMPT_VERSION, VQA_PROMPT_VERSION


class SceneServer(Node):
    def __init__(self):
        super().__init__('scene_server')
        defaults = {
            'camera_topic': '/rgb_image', 'stale_frame_threshold_sec': 2.0,
            'retained_scene_count': 10, 'runtime_data_directory': '.runtime/go2_vlm_scene',
            'image_save_format': 'png', 'jpeg_quality': 95,
            'enable_external_api_calls': False, 'default_provider': 'openai',
            'gemini_model': DEFAULT_MODELS['gemini'],
            'openai_model': DEFAULT_MODELS['openai'], 'qwen_model': DEFAULT_MODELS['qwen'],
            'api_jpeg_quality': 90, 'api_max_output_tokens': 256, 'api_timeout_sec': 30.0,
        }
        # Configuration is startup-only so runtime state cannot diverge from parameters.
        from rcl_interfaces.msg import ParameterDescriptor
        for name, value in defaults.items():
            self.declare_parameter(name, value, ParameterDescriptor(read_only=True))
        self.buffer = CameraBuffer(self.value('retained_scene_count'),
                                   self.value('stale_frame_threshold_sec'))
        if self.value('image_save_format') not in ('png', 'jpg', 'jpeg'):
            raise ValueError('image_save_format must be png, jpg, or jpeg')
        if not 1 <= self.value('jpeg_quality') <= 100:
            raise ValueError('jpeg_quality must be between 1 and 100')
        if not self.value('runtime_data_directory').strip():
            raise ValueError('runtime_data_directory must not be empty')
        if self.value('default_provider') not in ('openai', 'gemini'):
            raise ValueError('default_provider must be openai or gemini')
        self.query_log = QueryLog(self.value('runtime_data_directory'))
        self.bridge = CvBridge()
        self._first_frame = True
        self.create_subscription(Image, self.value('camera_topic'), self.on_image,
                                 qos_profile_sensor_data)
        self.create_service(CaptureScene, '/go2_vlm/capture_scene', self.capture)
        self.create_service(QueryScene, '/go2_vlm/query', self.query)
        self.last_query_metadata = None
        self.get_logger().info(
            f'Scene server ready; external API calls enabled: {self.value("enable_external_api_calls")}')

    def value(self, name):
        return self.get_parameter(name).value

    def on_image(self, message):
        received_at = time.monotonic()
        try:
            rgb = self.bridge.imgmsg_to_cv2(message, desired_encoding='rgb8')
            if rgb.shape[:2] != (message.height, message.width):
                raise ValueError('image dimensions do not match message')
            self.buffer.update(rgb, message.header.stamp.sec, message.header.stamp.nanosec,
                               message.header.frame_id, received_at)
            if self._first_frame:
                self.get_logger().info(
                    f'Received {message.width}x{message.height} {message.encoding}; internal RGB8')
                self._first_frame = False
        except Exception as exc:
            self.get_logger().warning(f'Rejected camera frame: {exc}', throttle_duration_sec=5.0)

    @staticmethod
    def metadata(response, scene):
        response.scene_id = scene.scene_id
        response.image_stamp.sec = scene.frame.stamp_sec
        response.image_stamp.nanosec = scene.frame.stamp_nanosec
        response.frame_id = scene.frame.frame_id

    def capture(self, request, response):
        try:
            scene = self.buffer.capture()
            self.metadata(response, scene)
            if request.save_image:
                response.saved_path = save_scene(
                    scene, self.value('runtime_data_directory'),
                    self.value('image_save_format'), self.value('jpeg_quality'))
            response.success = True
        except Exception as exc:
            response.error_message = str(exc)
        return response

    def query(self, request, response):
        started = time.monotonic()
        selected = request.provider or self.value('default_provider')
        operation = request.mode or 'describe'
        model = self.value(selected + '_model') if selected in ('openai', 'gemini') else ''
        response.provider, response.model = selected, model
        record = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'operation': operation, 'scene_id': request.scene_id,
            'image_rgb_sha256': None, 'image_jpeg_sha256': None,
            'provider': selected, 'model': model,
            'prompt_version': {'describe': PROMPT_VERSION, 'vqa': VQA_PROMPT_VERSION}.get(operation),
            'question': request.question.strip() if operation == 'vqa' else '',
            'response': '', 'attempts': [], 'attempt_count': 0,
            'input_tokens': None, 'output_tokens': None, 'total_tokens': None, 'raw_usage': {},
        }
        try:
            if operation not in ('describe', 'vqa'):
                raise ValueError('INVALID_REQUEST: mode must be describe or vqa')
            if operation == 'vqa' and not request.question.strip():
                raise ValueError('INVALID_REQUEST: vqa requires a question')
            if selected not in ('openai', 'gemini'):
                raise ValueError('INVALID_REQUEST: provider must be openai or gemini')
            scene = self.buffer.resolve(request.scene_id, request.refresh_frame)
            self.metadata(response, scene)
            result = query_scene(scene, operation, selected, model, QueryOptions(
                enable_external_api_calls=self.value('enable_external_api_calls'),
                jpeg_quality=self.value('api_jpeg_quality'),
                max_output_tokens=self.value('api_max_output_tokens'),
                timeout_sec=self.value('api_timeout_sec')), question=request.question)
            record.update(result.metadata)
            response.success = result.success
            response.answer = result.answer
            response.usage_json = json.dumps(result.raw_usage) if result.raw_usage else ''
            response.error_message = (f'{result.error_type}: {result.error_message}'
                                      if result.error_type else '')
        except (SceneError, ValueError) as exc:
            response.error_message = str(exc)
            record.update(status=str(exc).partition(':')[0], error_message=str(exc))
        except Exception:
            response.error_message = 'QUERY_ERROR: unable to process visual query'
            record.update(status='QUERY_ERROR', error_message=response.error_message)
        response.latency_sec = time.monotonic() - started
        record.update(latency_sec=response.latency_sec, response=response.answer,
                      image_stamp={'sec': response.image_stamp.sec, 'nanosec': response.image_stamp.nanosec},
                      frame_id=response.frame_id)
        self.last_query_metadata = record
        try:
            self.query_log.append(record)
        except Exception:
            response.success = False
            response.answer = ''
            response.error_message = 'QUERY_LOG_ERROR: unable to save query audit'
            self.get_logger().error('Unable to save sanitized query audit; details withheld')
        return response


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = SceneServer()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
