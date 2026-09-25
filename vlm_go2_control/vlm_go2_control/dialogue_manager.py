"""Terminal dialogue manager for the Go2 robot."""

import rclpy

from vlm_go2_control.command_parser import parse_command
from vlm_go2_control.task2_navigation import RoomNavigator


def main(args=None):
    """Run the terminal dialogue interface."""

    rclpy.init(args=args)

    navigator = RoomNavigator()

    print()
    print("====================================")
    print("      EE5112 Go2 Assistant")
    print("====================================")
    print("Type 'quit' to exit.")
    print()

    try:
        while True:

            user_input = input("You: ").strip()

            if user_input.lower() in ("quit", "exit"):
                print("Robot: Goodbye.")
                break

            command = parse_command(user_input)

            action = command.get("action", "chat")

            if action == "goto_room":

                room_id = command["room"]

                print(
                    f"Robot: Going to Room {room_id}..."
                )

                success, reply = navigator.goto_room(
                    room_id
                )

            elif action == "describe":

                reply = (
                    "Scene description is not "
                    "connected yet."
                )

            elif action == "approach":

                reply = (
                    "Object approach is not "
                    "connected yet."
                )

            elif action == "stop":

                reply = navigator.stop()

            else:

                reply = command.get(
                    "reply",
                    "I did not understand that command.",
                )

            print(f"Robot: {reply}")
            print()

    except KeyboardInterrupt:

        print()
        print("Robot: Shutting down.")

    finally:

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
