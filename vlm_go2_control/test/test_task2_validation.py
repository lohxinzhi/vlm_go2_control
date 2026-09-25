"""Test Task 2 command validation without using an LLM API."""

from vlm_go2_control.command_parser import CommandParser

def main():
    """Run local command-validation tests."""

    parser = CommandParser.__new__(
        CommandParser
    )

    tests = [
        {
            "name": "valid room",
            "input": {
                "action": "goto_room",
                "room": 3,
            },
            "expected_action": "goto_room",
        },

        {
            "name": "invalid room",
            "input": {
                "action": "goto_room",
                "room": 99,
            },
            "expected_action": "chat",
        },

        {
            "name": "invalid room type",
            "input": {
                "action": "goto_room",
                "room": "banana",
            },
            "expected_action": "chat",
        },

        {
            "name": "describe",
            "input": {
                "action": "describe",
            },
            "expected_action": "describe",
        },

        {
            "name": "valid approach",
            "input": {
                "action": "approach",
                "object": "red cup",
            },
            "expected_action": "approach",
        },

        {
            "name": "approach without object",
            "input": {
                "action": "approach",
            },
            "expected_action": "chat",
        },

        {
            "name": "stop",
            "input": {
                "action": "stop",
            },
            "expected_action": "stop",
        },

        {
            "name": "unsupported action",
            "input": {
                "action": "fly",
            },
            "expected_action": "chat",
        },
    ]

    passed = 0

    total = len(tests)

    print()
    print("========================================")
    print("      TASK 2 VALIDATION TESTS")
    print("========================================")
    print()

    for number, test in enumerate(
        tests,
        start=1,
    ):

        actual = parser.validate_command(
            test["input"]
        )

        actual_action = actual.get(
            "action"
        )

        success = (
            actual_action
            == test["expected_action"]
        )

        if success:
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"

        print(
            f"[{status}] "
            f"{number:02d}/{total} "
            f"{test['name']}"
        )

        print(
            "  Input:",
            test["input"],
        )

        print(
            "  Expected action:",
            test["expected_action"],
        )

        print(
            "  Actual:",
            actual,
        )

        print()

    print(
        f"Result: {passed}/{total} passed"
    )


if __name__ == "__main__":
    main()
