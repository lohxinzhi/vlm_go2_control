#!/usr/bin/env python3

import math
import time

from geometry_msgs.msg import PoseWithCovarianceStamped
import rclpy
from rclpy.node import Node


class SetInitialPose(Node):
    def __init__(self):
        super().__init__('set_initial_pose')
        self.declare_parameters(
            namespace='',
            parameters=[
                ('x', 0.0),
                ('y', 0.0),
                ('heading', math.radians(0.0)),
            ],
        )
        self.pub = self.create_publisher(PoseWithCovarianceStamped, '/initialpose', 10)
        self.timer = self.create_timer(0.5, self.publish_once)
        self.published = False
        self.start_time = time.monotonic()

    def publish_once(self):
        if self.published:
            self.destroy_timer(self.timer)
            return
        if time.monotonic() - self.start_time < 3.0:
            return

        x = float(self.get_parameter('x').value)
        y = float(self.get_parameter('y').value)
        heading = float(self.get_parameter('heading').value)

        msg = PoseWithCovarianceStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        msg.pose.pose.position.x = x
        msg.pose.pose.position.y = y
        msg.pose.pose.position.z = 0.0
        q = self._yaw_to_quat(heading)
        msg.pose.pose.orientation.x = q[0]
        msg.pose.pose.orientation.y = q[1]
        msg.pose.pose.orientation.z = q[2]
        msg.pose.pose.orientation.w = q[3]
        msg.pose.covariance = [
            0.05, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.05, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0, 0.0, 0.0, 0.05,
        ]

        self.pub.publish(msg)
        self.get_logger().info(
            f'Publishing initial pose estimate: x={x}, y={y}, heading={heading} rad'
        )
        self.published = True
        self.destroy_timer(self.timer)

    @staticmethod
    def _yaw_to_quat(yaw):
        cy = math.cos(yaw * 0.5)
        sy = math.sin(yaw * 0.5)
        return (0.0, 0.0, sy, cy)


def main(args=None):
    rclpy.init(args=args)
    node = SetInitialPose()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
