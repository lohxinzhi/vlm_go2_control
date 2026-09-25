"""Navigate the Go2 robot to predefined room waypoints."""

import math
import os

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
import rclpy
import yaml


class RoomNavigator:
    """Handle navigation to predefined rooms using Nav2."""

    def __init__(self):
        """Create the Nav2 interface and load the room configuration."""

        self.navigator = BasicNavigator()

        package_dir = get_package_share_directory(
            "vlm_go2_control"
        )

        rooms_file = os.path.join(
            package_dir,
            "params",
            "rooms.yaml",
        )

        with open(
            rooms_file,
            "r",
            encoding="utf-8",
        ) as file:
            data = yaml.safe_load(file)

        self.rooms = {
            int(room_id): room
            for room_id, room in data["rooms"].items()
        }

    def make_pose(self, x, y, yaw_deg):
        """Convert x, y and yaw into a ROS PoseStamped goal."""

        pose = PoseStamped()

        pose.header.frame_id = "map"

        pose.header.stamp = (
            self.navigator
            .get_clock()
            .now()
            .to_msg()
        )

        pose.pose.position.x = float(x)
        pose.pose.position.y = float(y)
        pose.pose.position.z = 0.0

        yaw_rad = math.radians(
            float(yaw_deg)
        )

        pose.pose.orientation.z = math.sin(
            yaw_rad / 2.0
        )

        pose.pose.orientation.w = math.cos(
            yaw_rad / 2.0
        )

        return pose

    def goto_room(self, room_id):
        """Navigate to a room and return success plus a reply."""

        room_id = int(room_id)

        if room_id not in self.rooms:
            return (
                False,
                f"Room {room_id} is not defined.",
            )

        room = self.rooms[room_id]

        goal_pose = self.make_pose(
            room["x"],
            room["y"],
            room["yaw_deg"],
        )

        room_name = room["name"]

        print(
            f"Navigating to Room {room_id} "
            f"({room_name})..."
        )

        self.navigator.goToPose(
            goal_pose
        )

        while not self.navigator.isTaskComplete():

            rclpy.spin_once(
                self.navigator,
                timeout_sec=0.1,
            )

        result = self.navigator.getResult()

        if result == TaskResult.SUCCEEDED:

            return (
                True,
                f"I have arrived at Room {room_id}, "
                f"the {room_name}.",
            )

        if result == TaskResult.CANCELED:

            return (
                False,
                f"Navigation to Room {room_id} "
                "was canceled.",
            )

        return (
            False,
            f"I could not reach Room {room_id}.",
        )

    def stop(self):
        """Cancel the current Nav2 navigation task."""

        self.navigator.cancelTask()

        return "Navigation stopped.""""Navigate the Go2 robot to predefined room waypoints."""

import math
import os

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
import rclpy
import yaml


class RoomNavigator:
    """Handle navigation to predefined rooms using Nav2."""

    def __init__(self):
        """Create the Nav2 interface and load the room configuration."""

        self.navigator = BasicNavigator()

        package_dir = get_package_share_directory(
            "vlm_go2_control"
        )

        rooms_file = os.path.join(
            package_dir,
            "params",
            "rooms.yaml",
        )

        with open(
            rooms_file,
            "r",
            encoding="utf-8",
        ) as file:
            data = yaml.safe_load(file)

        self.rooms = {
            int(room_id): room
            for room_id, room in data["rooms"].items()
        }

    def make_pose(self, x, y, yaw_deg):
        """Convert x, y and yaw into a ROS PoseStamped goal."""

        pose = PoseStamped()

        pose.header.frame_id = "map"

        pose.header.stamp = (
            self.navigator
            .get_clock()
            .now()
            .to_msg()
        )

        pose.pose.position.x = float(x)
        pose.pose.position.y = float(y)
        pose.pose.position.z = 0.0

        yaw_rad = math.radians(
            float(yaw_deg)
        )

        pose.pose.orientation.z = math.sin(
            yaw_rad / 2.0
        )

        pose.pose.orientation.w = math.cos(
            yaw_rad / 2.0
        )

        return pose

    def goto_room(self, room_id):
        """Navigate to a room and return success plus a reply."""

        room_id = int(room_id)

        if room_id not in self.rooms:
            return (
                False,
                f"Room {room_id} is not defined.",
            )

        room = self.rooms[room_id]

        goal_pose = self.make_pose(
            room["x"],
            room["y"],
            room["yaw_deg"],
        )

        room_name = room["name"]

        print(
            f"Navigating to Room {room_id} "
            f"({room_name})..."
        )

        self.navigator.goToPose(
            goal_pose
        )

        while not self.navigator.isTaskComplete():

            rclpy.spin_once(
                self.navigator,
                timeout_sec=0.1,
            )

        result = self.navigator.getResult()

        if result == TaskResult.SUCCEEDED:

            return (
                True,
                f"I have arrived at Room {room_id}, "
                f"the {room_name}.",
            )

        if result == TaskResult.CANCELED:

            return (
                False,
                f"Navigation to Room {room_id} "
                "was canceled.",
            )

        return (
            False,
            f"I could not reach Room {room_id}.",
        )

    def stop(self):
        """Cancel the current Nav2 navigation task."""

        self.navigator.cancelTask()

        return "Navigation stopped."
