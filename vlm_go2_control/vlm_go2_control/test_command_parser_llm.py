"""Interactive parser-only test for Task 2."""

import argparse

from vlm_go2_control.command_parser import CommandParser


def main():
    """Run an interactive parser test."""

    argument_parser = (
        argparse.ArgumentParser()
    )

    argument_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use offline mock parsing.",
    )

    args = (
        argument_parser
        .parse_args()
    )

    parser = CommandParser(
        use_mock=args.mock
    )

    print()
    print(
        "===================================="
    )

    print(
        "     Task 2 Command Parser"
    )

    print(
        "===================================="
    )

    print(
        "Robot movement is disabled "
        "in this test."
    )

    print()

    while True:

        user_input = input(
            "You: "
        ).strip()

        if user_input.lower() in (
            "quit",
            "exit",
        ):
            break

        command = parser.parse(
            user_input
        )

        print(
            "Parsed:",
            command,
        )

        print()


if __name__ == "__main__":
    main()
