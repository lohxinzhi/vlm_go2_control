# Copyright 2026 Xinzhi
# SPDX-License-Identifier: Apache-2.0

"""Check measured-motion preservation and the odometry TF decomposition."""

import math

from geometry_msgs.msg import Quaternion
from nav_msgs.msg import Odometry
import pytest

from vlm_go2_control.simulation_odometry import multiply_quaternions, project_odometry


def test_tilted_body_on_raised_floor():
    """Compose the two TF edges back into the original measured body pose."""
    measured = Odometry()
    measured.header.frame_id = 'odom'
    measured.header.stamp.sec = 12
    measured.child_frame_id = 'base_link'
    measured.pose.pose.position.x = 2.5
    measured.pose.pose.position.y = -1.2
    measured.pose.pose.position.z = 4.3
    yaw, pitch = 0.7, 0.2
    measured.pose.pose.orientation = multiply_quaternions(
        Quaternion(z=math.sin(yaw / 2), w=math.cos(yaw / 2)),
        Quaternion(y=math.sin(pitch / 2), w=math.cos(pitch / 2)))
    measured.twist.twist.linear.x = 0.2
    planar, odom_tf, body_tf = project_odometry(measured, 4.0)
    assert planar.pose.pose.position.x == 2.5
    assert planar.pose.pose.position.y == -1.2
    assert planar.pose.pose.position.z == 0.0
    assert planar.twist.twist.linear.x == pytest.approx(0.2 * math.cos(pitch))
    assert body_tf.transform.translation.z == pytest.approx(0.3)
    recomposed = multiply_quaternions(
        odom_tf.transform.rotation, body_tf.transform.rotation)
    for component in ('x', 'y', 'z', 'w'):
        assert getattr(recomposed, component) == pytest.approx(
            getattr(measured.pose.pose.orientation, component))
    assert odom_tf.header.stamp == body_tf.header.stamp == measured.header.stamp
    assert odom_tf.child_frame_id == body_tf.header.frame_id == 'base_footprint'
    assert body_tf.child_frame_id == 'base_link'
    assert measured.pose.pose.position.z == 4.3


def test_measured_translation_is_not_frozen():
    """The published position follows new Gazebo measurements without contacts."""
    measured = Odometry()
    measured.pose.pose.orientation.w = 1.0
    first, _, _ = project_odometry(measured, 0.0)
    measured.pose.pose.position.x = 0.47
    measured.twist.twist.linear.x = 0.1
    second, _, _ = project_odometry(measured, 0.0)
    assert second.pose.pose.position.x - first.pose.pose.position.x == pytest.approx(0.47)
    assert second.twist.twist.linear.x == pytest.approx(0.1)


def test_invalid_orientation_is_rejected():
    """Do not publish invalid rotations into the shared TF tree."""
    measured = Odometry()
    measured.pose.pose.orientation.w = 0.0
    with pytest.raises(ValueError, match='Invalid orientation'):
        project_odometry(measured, 0.0)
