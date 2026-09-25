"""Evaluate the Task 2 LLM command parser."""

from task2_test_cases import TEST_CASES

from vlm_go2_control.command_parser import CommandParser


def commands_match(expected, actual):
    """Check whether the actual command matches the expected command."""

    # First, the action itself must match.
    if actual.get("action") != expected.get("action"):
        return False

    action = expected.get("action")

    # For navigation commands, both the action and room number
    # must be correct.
    if action == "goto_room":
        return (
            actual.get("room")
            == expected.get("room")
        )

    # For approach commands, check that the expected object
    # appears in the object name returned by the LLM.
    if action == "approach":

        expected_object = expected.get(
            "object",
            "",
        ).lower()

        actual_object = actual.get(
            "object",
            "",
        ).lower()

        return (
            expected_object
            in actual_object
        )

    # For describe, stop, and chat, matching the action
    # is enough for this evaluation.
    return True


def main():
    """Run all Task 2 parser test cases."""

    total = len(TEST_CASES)

    correct = 0

    category_results = {}

    failures = []

    print()
    print("========================================")
    print("       TASK 2 PARSER EVALUATION")
    print("========================================")
    print()

    for number, test_case in enumerate(
        TEST_CASES,
        start=1,
    ):

        # Create a fresh parser for every test.
        #
        # This prevents conversation history from one
        # test influencing another test.
        parser = CommandParser()

        user_input = test_case[
            "input"
        ]

        expected = test_case[
            "expected"
        ]

        category = test_case[
            "category"
        ]

        print(
            f"Running test "
            f"{number:02d}/{total}..."
        )

        # Send the natural-language command to the LLM.
        actual = parser.parse(
            user_input
        )

        # --------------------------------------------------
        # API FAILURE CHECK
        # --------------------------------------------------
        #
        # command_parser.py returns this specific response
        # when the OpenAI API cannot be reached or used.
        #
        # We do NOT want an API failure to be counted as
        # a parser failure, because that would make the
        # calculated accuracy meaningless.
        #
        if (
            actual.get("action") == "chat"
            and actual.get("reply")
            == (
                "The language model is currently "
                "unavailable."
            )
        ):

            print()
            print("========================================")
            print("         EVALUATION STOPPED")
            print("========================================")
            print()

            print(
                "The LLM API is unavailable."
            )

            print(
                "No parser accuracy has been "
                "calculated."
            )

            print()
            print(
                "Check OPENAI_API_KEY, API access, "
                "credits, and network connectivity."
            )

            return

        # Compare the actual command with the expected one.
        passed = commands_match(
            expected,
            actual,
        )

        # Create a result counter for this category
        # the first time we encounter it.
        if category not in category_results:

            category_results[
                category
            ] = {
                "correct": 0,
                "total": 0,
            }

        category_results[
            category
        ]["total"] += 1

        # Record whether this test passed.
        if passed:

            correct += 1

            category_results[
                category
            ]["correct"] += 1

            status = "PASS"

        else:

            status = "FAIL"

            failures.append(
                {
                    "input": user_input,
                    "expected": expected,
                    "actual": actual,
                    "category": category,
                }
            )

        # Print the result for this individual test.
        print(
            f"[{status}] "
            f"{number:02d}/{total}"
        )

        print(
            "  Input:",
            user_input,
        )

        print(
            "  Expected:",
            expected,
        )

        print(
            "  Actual:",
            actual,
        )

        print(
            "  Category:",
            category,
        )

        print()

    # --------------------------------------------------
    # OVERALL ACCURACY
    # --------------------------------------------------

    accuracy = (
        correct / total
    ) * 100.0

    print("========================================")
    print("                RESULTS")
    print("========================================")
    print()

    print(
        f"Correct: {correct}/{total}"
    )

    print(
        f"Accuracy: {accuracy:.1f}%"
    )

    print(
        f"Failures: {len(failures)}"
    )

    print()

    # --------------------------------------------------
    # CATEGORY ACCURACY
    # --------------------------------------------------

    print("Category results:")
    print()

    for category, results in (
        category_results.items()
    ):

        category_correct = results[
            "correct"
        ]

        category_total = results[
            "total"
        ]

        category_accuracy = (
            category_correct
            / category_total
        ) * 100.0

        print(
            f"  {category}: "
            f"{category_correct}/"
            f"{category_total} "
            f"({category_accuracy:.1f}%)"
        )

    # --------------------------------------------------
    # FAILURE ANALYSIS
    # --------------------------------------------------

    if failures:

        print()
        print("========================================")
        print("            FAILURE ANALYSIS")
        print("========================================")
        print()

        for number, failure in enumerate(
            failures,
            start=1,
        ):

            print(
                f"Failure {number}:"
            )

            print(
                "  Input:",
                failure["input"],
            )

            print(
                "  Category:",
                failure["category"],
            )

            print(
                "  Expected:",
                failure["expected"],
            )

            print(
                "  Actual:",
                failure["actual"],
            )

            print()

    else:

        print()
        print(
            "No parser failures were recorded."
        )


if __name__ == "__main__":
    main()
