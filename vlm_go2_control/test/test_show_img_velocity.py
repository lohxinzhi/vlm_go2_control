"""Tests for the command direction overlay on camera frames."""

import numpy as np
import pytest
from geometry_msgs.msg import Twist

from vlm_go2_control import robot_dashboard


@pytest.mark.parametrize('linear,angular,active_index', [
    (0.5, 0.0, 0),
    (-0.5, 0.0, 1),
    (0.0, 0.5, 2),
    (0.0, -0.5, 3),
    (0.0, 0.0, None),
])
def test_velocity_direction_colors(monkeypatch, linear, angular, active_index):
    """Only the arrow matching the ROS velocity sign becomes bright green."""
    calls = []
    monkeypatch.setattr(
        robot_dashboard.cv2, 'arrowedLine',
        lambda _frame, start, tip, color, *_args, **_kwargs:
        calls.append((start, tip, color)))
    command = Twist()
    command.linear.x = linear
    command.angular.z = angular

    robot_dashboard.draw_velocity_arrows(
        np.zeros((240, 320, 3), dtype=np.uint8), command)

    assert len(calls) == 4
    assert calls[0][1][1] < calls[0][0][1]  # Up.
    assert calls[1][1][1] > calls[1][0][1]  # Down.
    assert calls[2][1][0] < calls[2][0][0]  # Left.
    assert calls[3][1][0] > calls[3][0][0]  # Right.
    for index, (_, _, color) in enumerate(calls):
        expected = (robot_dashboard.ACTIVE_ARROW_COLOR if index == active_index
                    else robot_dashboard.INACTIVE_ARROW_COLOR)
        assert color == expected


def test_velocity_arrows_render_on_frame():
    """The overlay is drawn into the displayed image."""
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    robot_dashboard.draw_velocity_arrows(frame, Twist())
    assert frame.any()
