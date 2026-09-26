import time

import cv2
import rclpy
from cv_bridge import CvBridge, CvBridgeError
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32
from vision_msgs.msg import Detection2D


INACTIVE_ARROW_COLOR = (100, 140, 100)  # Muted green in OpenCV BGR order.
ACTIVE_ARROW_COLOR = (0, 255, 0)
VELOCITY_DEADBAND = 1e-3
DETECTION_DISPLAY_SECONDS = 3.0


def draw_velocity_arrows(frame, command):
    """Draw command direction arrows along the four image edges."""
    height, width = frame.shape[:2]
    scale = min(width, height)
    margin = max(6, round(scale * 0.04))
    length = max(18, round(scale * 0.13))
    thickness = max(3, round(scale * 0.015))
    center_x, center_y = width // 2, height // 2
    arrows = (
        ((center_x, margin + length), (center_x, margin),
         command.linear.x > VELOCITY_DEADBAND),
        ((center_x, height - margin - length), (center_x, height - margin),
         command.linear.x < -VELOCITY_DEADBAND),
        ((margin + length, center_y), (margin, center_y),
         command.angular.z > VELOCITY_DEADBAND),
        ((width - margin - length, center_y), (width - margin, center_y),
         command.angular.z < -VELOCITY_DEADBAND),
    )
    for start, tip, active in arrows:
        color = ACTIVE_ARROW_COLOR if active else INACTIVE_ARROW_COLOR
        cv2.arrowedLine(frame, start, tip, color, thickness,
                        line_type=cv2.LINE_AA, tipLength=0.45)


class ImageAndBoundingBoxViewer(Node):
    """Display camera images with detection boxes and velocity arrows."""

    def __init__(self):
        super().__init__('image_and_bounding_box_viewer')

        self.image_topic = self.declare_parameter(
            'image_topic', '/rgb_image').value
        self.bounding_box_topic = self.declare_parameter(
            'bounding_box_topic', '/ground_bbox').value
        self.window_name = 'Go2 camera'
        self.bridge = CvBridge()

        self.image_subscription = self.create_subscription(
            Image, self.image_topic, self.image_callback, 10)
        self.create_subscription(
            Detection2D,
            self.bounding_box_topic,
            self.bounding_box_callback,
            10,
        )
        self.front_distance_subscription = self.create_subscription(
            Float32,
            '/front_distance',
            self.front_distance_callback,
            10,
        )
        self.create_subscription(Twist, '/cmd_vel', self.velocity_callback, 10)

        self.latest_detection = None
        self.latest_detection_received_at = None
        self.front_distance = None
        self.latest_velocity = Twist()
        self.get_logger().info(
            f'Subscribing to {self.image_topic} and '
            f'{self.bounding_box_topic}')

    def bounding_box_callback(self, message: Detection2D):
        """Store the newest detection and restart its display timeout."""
        self.latest_detection = message
        self.latest_detection_received_at = time.monotonic()

    def visible_detection(self):
        """Return the current detection only during its display window."""
        if self.latest_detection is None:
            return None
        if (self.latest_detection_received_at is None or
                time.monotonic() - self.latest_detection_received_at >=
                DETECTION_DISPLAY_SECONDS):
            self.latest_detection = None
            self.latest_detection_received_at = None
            return None
        return self.latest_detection

    def front_distance_callback(self, message: Float32):
        """Store the latest forward distance in meters."""
        self.front_distance = message.data

    def velocity_callback(self, message: Twist):
        """Store the latest command for the next displayed frame."""
        self.latest_velocity = message

    def image_callback(self, message: Image):
        """Convert and display an image with the newest detection boxes."""
        try:
            frame = self.bridge.imgmsg_to_cv2(message, desired_encoding='bgr8')
        except CvBridgeError as error:
            self.get_logger().error(f'Could not convert image: {error}')
            return

        detection = self.visible_detection()
        if detection is not None:
            self.draw_detection(frame, detection)
        draw_velocity_arrows(frame, self.latest_velocity)

        cv2.imshow(self.window_name, frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            rclpy.shutdown()

    def draw_detection(self, frame, detection):
        """Draw one vision_msgs Detection2D on an OpenCV frame."""
        center = detection.bbox.center.position
        width = detection.bbox.size_x
        height = detection.bbox.size_y

        x1 = max(0, round(center.x - width / 2))
        y1 = max(0, round(center.y - height / 2))
        x2 = min(frame.shape[1] - 1, round(center.x + width / 2))
        y2 = min(frame.shape[0] - 1, round(center.y + height / 2))
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        label = (
            f'{self.front_distance:.2f} m'
            if self.front_distance is not None else '-- m'
        )
        cv2.putText(
            frame,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    def destroy_node(self):
        cv2.destroyAllWindows()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    viewer = ImageAndBoundingBoxViewer()
    try:
        rclpy.spin(viewer)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
