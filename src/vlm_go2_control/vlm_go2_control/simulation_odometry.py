# Copyright 2026 Xinzhi
# SPDX-License-Identifier: Apache-2.0

"""Provide simulation odometry and body transforms from Gazebo measurements."""

from copy import deepcopy
import math

from geometry_msgs.msg import Quaternion, TransformStamped
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from tf2_ros import TransformBroadcaster


def multiply_quaternions(left, right):
    """Compose rotations, using ROS quaternion component ordering."""
    return Quaternion(
        x=left.w * right.x + left.x * right.w + left.y * right.z - left.z * right.y,
        y=left.w * right.y - left.x * right.z + left.y * right.w + left.z * right.x,
        z=left.w * right.z + left.x * right.y - left.y * right.x + left.z * right.w,
        w=left.w * right.w - left.x * right.x - left.y * right.y - left.z * right.z,
    )


def rotate_vector(rotation, vector):
    """Express a vector in the frame reached by a quaternion rotation."""
    pure = Quaternion(x=vector.x, y=vector.y, z=vector.z, w=0.0)
    inverse = Quaternion(
        x=-rotation.x, y=-rotation.y, z=-rotation.z, w=rotation.w)
    return multiply_quaternions(multiply_quaternions(rotation, pure), inverse)


def project_odometry(measured, ground_height):
    """Split a 3D body pose into planar odometry and the remaining body motion."""
    orientation = measured.pose.pose.orientation
    norm = math.sqrt(sum(value * value for value in (
        orientation.x, orientation.y, orientation.z, orientation.w)))
    if not math.isfinite(norm) or norm < 1.0e-9:
        raise ValueError('Invalid orientation in simulation odometry')
    orientation = Quaternion(
        x=orientation.x / norm, y=orientation.y / norm,
        z=orientation.z / norm, w=orientation.w / norm)
    yaw = math.atan2(
        2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1.0 - 2.0 * (orientation.y ** 2 + orientation.z ** 2))
    planar_rotation = Quaternion(z=math.sin(yaw / 2.0), w=math.cos(yaw / 2.0))
    inverse_yaw = Quaternion(z=-planar_rotation.z, w=planar_rotation.w)
    body_rotation = multiply_quaternions(inverse_yaw, orientation)

    planar = deepcopy(measured)
    planar.child_frame_id = 'base_footprint'
    planar.pose.pose.position.z = 0.0
    planar.pose.pose.orientation = planar_rotation
    # Gazebo expresses twist in base_link. Nav2's odometry uses base_footprint.
    linear = rotate_vector(body_rotation, measured.twist.twist.linear)
    angular = rotate_vector(body_rotation, measured.twist.twist.angular)
    planar.twist.twist.linear.x = linear.x
    planar.twist.twist.linear.y = linear.y
    planar.twist.twist.linear.z = 0.0
    planar.twist.twist.angular.x = 0.0
    planar.twist.twist.angular.y = 0.0
    planar.twist.twist.angular.z = angular.z

    odom_transform = TransformStamped()
    odom_transform.header = deepcopy(measured.header)
    odom_transform.child_frame_id = 'base_footprint'
    odom_transform.transform.translation.x = measured.pose.pose.position.x
    odom_transform.transform.translation.y = measured.pose.pose.position.y
    odom_transform.transform.rotation = planar_rotation

    body_transform = TransformStamped()
    body_transform.header.stamp = deepcopy(measured.header.stamp)
    body_transform.header.frame_id = 'base_footprint'
    body_transform.child_frame_id = 'base_link'
    body_transform.transform.translation.z = measured.pose.pose.position.z - ground_height
    body_transform.transform.rotation = body_rotation
    return planar, odom_transform, body_transform


class SimulationOdometry(Node):
    """Publish a coherent odometry/TF pair at each Gazebo measurement timestamp."""

    def __init__(self):
        """Connect measured simulation pose to Nav2's planar odometry interface."""
        super().__init__('simulation_odometry')
        self.declare_parameter('ground_height', 0.0)
        self.ground_height = self.get_parameter('ground_height').value
        self.publisher = self.create_publisher(Odometry, 'odom', 10)
        self.broadcaster = TransformBroadcaster(self)
        self.subscription = self.create_subscription(
            Odometry, 'odom/ground_truth', self.receive_odometry, qos_profile_sensor_data)

    def receive_odometry(self, measured):
        """Use measured motion rather than inferred contact states."""
        if measured.header.frame_id != 'odom' or measured.child_frame_id != 'base_link':
            self.get_logger().error(
                'Expected ground-truth frames odom -> base_link', throttle_duration_sec=5.0)
            return
        try:
            planar, odom_transform, body_transform = project_odometry(
                measured, self.ground_height)
        except ValueError as error:
            self.get_logger().error(str(error), throttle_duration_sec=5.0)
            return
        self.broadcaster.sendTransform([odom_transform, body_transform])
        self.publisher.publish(planar)


def main(args=None):
    """Run the simulation-only odometry adapter."""
    rclpy.init(args=args)
    node = SimulationOdometry()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
