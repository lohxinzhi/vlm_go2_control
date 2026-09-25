"""Evaluate the Task 2 LLM command parser."""

from task2_test_cases import TEST_CASES

from vlm_go2_control.command_parser_llm import CommandParser


def commands_match(expected, actual):
    """Return True when an actual command matches the expected command."""

    if actual.get("action") != expected.get("action"):
        return False

    action = expected.get("action")

    if action == "goto_room":
        return (
            actual.get("room")
            == expected.get("room")
        )

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
        # This ensures that Test 2 is not influenced
        # by conversation history from Test 1.
        parser = CommandParser()

        user_input = test_case["input"]

        expected = test_case["expected"]

        category = test_case["category"]

        actual = parser.parse(
            user_input
        )

        passed = commands_match(
            expected,
            actual,
        )

        if category not in category_results:
            category_results[category] = {
                "correct": 0,
                "total": 0,
            }

        category_results[
            category
        ]["total"] += 1

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

    accuracy = (
        correct / total
    ) * 100.0

    print("========================================")
    print("                RESULTS")
    print("========================================")
    print()

    print(
        f"Overall: {correct}/{total}"
    )

    print(
        f"Accuracy: {accuracy:.1f}%"
    )

    print()

    print("Category results:")

    for category, results in category_results.items():

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

    if failures:

        print()
        print("========================================")
        print("            FAILURE ANALYSIS")
        print("========================================")
        print()

        for failure in failures:

            print(
                "Input:",
                failure["input"],
            )

            print(
                "Category:",
                failure["category"],
            )

            print(
                "Expected:",
                failure["expected"],
            )

            print(
                "Actual:",
                failure["actual"],
            )

            print()


if __name__ == "__main__":
    main()
