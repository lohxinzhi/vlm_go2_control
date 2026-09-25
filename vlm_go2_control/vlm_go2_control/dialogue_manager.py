"""Terminal dialogue manager for Task 2."""

import argparse

import rclpy

from vlm_go2_control.command_parser import CommandParser
from vlm_go2_control.task2_navigation import RoomNavigator


def create_argument_parser():
    """Create command-line arguments."""

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Use the offline mock parser "
            "instead of the OpenAI API."
        ),
    )

    return parser


def main(args=None):
    """Run the Task 2 terminal dialogue manager."""

    argument_parser = (
        create_argument_parser()
    )

    parsed_args, ros_args = (
        argument_parser
        .parse_known_args()
    )

    rclpy.init(
        args=ros_args
    )

    try:
        parser = CommandParser(
            use_mock=parsed_args.mock
        )

    except RuntimeError as error:

        print()
        print(
            "Parser setup error:",
            error,
        )

        print()

        if rclpy.ok():
            rclpy.shutdown()

        return

    navigator = RoomNavigator()

    print()
    print(
        "===================================="
    )

    print(
        "      EE5112 Go2 Assistant"
    )

    print(
        "===================================="
    )

    if parsed_args.mock:
        print(
            "Parser mode: MOCK"
        )

    else:
        print(
            "Parser mode: OpenAI LLM"
        )

    print(
        "Type 'quit' to exit."
    )

    print()

    try:

        while True:

            user_input = input(
                "You: "
            ).strip()

            if user_input.lower() in (
                "quit",
                "exit",
            ):

                print(
                    "Robot: Goodbye."
                )

                break

            command = parser.parse(
                user_input
            )

            action = command.get(
                "action",
                "chat",
            )

            if action == "goto_room":

                room_id = command[
                    "room"
                ]

                print(
                    f"Robot: Going to "
                    f"Room {room_id}..."
                )

                success, reply = (
                    navigator.goto_room(
                        room_id
                    )
                )

            elif action == "describe":

                reply = (
                    "Scene description is not "
                    "connected yet."
                )

            elif action == "approach":

                object_name = command.get(
                    "object",
                    "object",
                )

                reply = (
                    f"Object approach for "
                    f"'{object_name}' is not "
                    "connected yet."
                )

            elif action == "stop":

                reply = (
                    navigator.stop()
                )

            else:

                reply = command.get(
                    "reply",
                    (
                        "I did not understand "
                        "that command."
                    ),
                )

            print(
                f"Robot: {reply}"
            )

            print()

    except KeyboardInterrupt:

        print()
        print(
            "Robot: Shutting down."
        )

    finally:

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
