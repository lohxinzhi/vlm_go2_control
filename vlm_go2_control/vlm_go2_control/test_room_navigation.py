"""Manual test program for Task 2 room navigation."""

import sys

import rclpy

from vlm_go2_control.task2_navigation import RoomNavigator


def main():
    """Navigate the Go2 to a room specified by the user."""

    if len(sys.argv) != 2:
        print(
            "Usage: python3 -m "
            "vlm_go2_control.test_room_navigation <room_id>"
        )
        return

    try:
        room_id = int(sys.argv[1])

    except ValueError:
        print("Room ID must be a number.")
        return

    rclpy.init()

    navigator = RoomNavigator()

    try:
        success, message = navigator.goto_room(room_id)

        print()
        print("Navigation result:")
        print(message)

    except KeyboardInterrupt:
        print()
        print("Navigation interrupted by user.")

        navigator.stop()

    finally:
        navigator.navigator.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
