"""Navigate to a named room through a GoToRoom action."""

import math
import os
from threading import Event

from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
import yaml

import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from vlm_go2_interfaces.action import GoToRoom


class GoToRoomServer(Node):
    """Translate room IDs to Nav2 poses and report completion to the client."""

    def __init__(self):
        super().__init__('goto_room_server')
        room_path = os.path.join(
            get_package_share_directory('go2_house_world'),
            'params', 'bto_rooms.yaml')
        with open(room_path, 'r', encoding='utf-8') as room_file:
            self.rooms = yaml.safe_load(room_file)['rooms']
        group = ReentrantCallbackGroup()
        self.nav_client = ActionClient(
            self, NavigateToPose, '/navigate_to_pose', callback_group=group)
        self.server = ActionServer(
            self, GoToRoom, '/go_to_room', self.execute,
            goal_callback=self.accept_goal, cancel_callback=self.cancel_goal,
            callback_group=group)

    def accept_goal(self, request):
        return (GoalResponse.ACCEPT if request.room_id in self.rooms
                else GoalResponse.REJECT)

    def cancel_goal(self, _goal_handle):
        return CancelResponse.ACCEPT

    def make_pose(self, room):
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(room['x'])
        pose.pose.position.y = float(room['y'])
        yaw = math.radians(room['yaw_deg'])
        pose.pose.orientation.z = math.sin(yaw / 2.0)
        pose.pose.orientation.w = math.cos(yaw / 2.0)
        return pose

    @staticmethod
    def wait_for_future(future, goal_handle=None):
        ready = Event()
        future.add_done_callback(lambda _: ready.set())
        while rclpy.ok() and not ready.wait(0.2):
            if goal_handle is not None and goal_handle.is_cancel_requested:
                return None
        return future.result() if ready.is_set() else None

    def execute(self, goal_handle):
        room_id = goal_handle.request.room_id
        room_name = self.rooms[room_id]['name']
        result = GoToRoom.Result()
        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            result.message = 'Navigation server unavailable.'
            goal_handle.abort()
            return result
        goal_handle.publish_feedback(GoToRoom.Feedback(status='Navigating'))
        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = self.make_pose(self.rooms[room_id])
        nav_handle = self.wait_for_future(self.nav_client.send_goal_async(nav_goal))
        if nav_handle is None:
            result.message = 'Navigation goal could not be sent.'
            goal_handle.abort()
            return result
        if not nav_handle.accepted:
            result.message = 'Navigation goal rejected.'
            goal_handle.abort()
            return result
        nav_future = nav_handle.get_result_async()
        while rclpy.ok() and not nav_future.done():
            if goal_handle.is_cancel_requested:
                self.wait_for_future(nav_handle.cancel_goal_async())
                result.message = f'Navigation to {room_name}, room {room_id}, was canceled.'
                goal_handle.canceled()
                return result
            Event().wait(0.2)
        if not nav_future.done():
            result.message = 'Navigation interrupted.'
            goal_handle.abort()
            return result
        status = nav_future.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            result.success = True
            result.message = f'I have arrived at {room_name}, room {room_id}.'
            goal_handle.succeed()
        elif status == GoalStatus.STATUS_CANCELED:
            result.message = f'Navigation to {room_name}, room {room_id}, was canceled.'
            goal_handle.canceled()
        else:
            result.message = f'Could not reach {room_name}, room {room_id}: FAILED.'
            goal_handle.abort()
        return result


def main():
    rclpy.init()
    node = GoToRoomServer()
    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
