"""Interactive test for the Task 2 LLM command parser."""

from vlm_go2_control.command_parser_llm import CommandParser


def main():
    """Run an interactive parser-only conversation."""

    parser = CommandParser()

    print()
    print("========================================")
    print("       TASK 2 LLM PARSER TEST")
    print("========================================")
    print()
    print("This does not control the robot.")
    print("Type 'quit' to exit.")
    print()

    while True:

        user_input = input(
            "You: "
        ).strip()

        if user_input.lower() in (
            "quit",
            "exit",
        ):

            print(
                "Parser test ended."
            )

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
