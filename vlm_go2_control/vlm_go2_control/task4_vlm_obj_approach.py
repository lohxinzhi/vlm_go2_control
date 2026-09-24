import argparse
import math
import os

from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator
# Retained for the forthcoming VLM client integration.
from openai import OpenAI  # noqa: F401
import rclpy
import yaml

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


def main():
    """Start Nav2 navigation and drive the robot to the selected room."""
    parser = argparse.ArgumentParser(
        description='Navigate the Go2 robot to a room from bto_rooms.yaml.')
    parser.add_argument(
        'room', type=int, help='Room number to navigate to, for example 4')
    args, _ = parser.parse_known_args()

    rclpy.init()
    nav = BasicNavigator()
    try:
        nav.get_logger().info('Waiting for Nav2 to become active...')
        nav.setInitialPose(make_pose(nav, -0.5, 0.0, -1.15))
        nav.waitUntilNav2Active()

        world_dir = get_package_share_directory('go2_house_world')
        room_yaml_path = os.path.join(world_dir, 'params', 'bto_rooms.yaml')
        with open(room_yaml_path, 'r', encoding='utf-8') as room_file:
            rooms = yaml.safe_load(room_file)['rooms']

        result = goto_room(args.room, nav, rooms)
        nav.get_logger().info(
            f'Navigation to room {args.room} finished: {result}')
    finally:
        nav.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
