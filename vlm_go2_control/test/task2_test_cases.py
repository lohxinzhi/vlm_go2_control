"""Test cases for Task 2 natural-language command parsing."""


TEST_CASES = [
    # ==================================================
    # A. Basic room navigation
    # ==================================================

    {
        "input": "Go to Room 0.",
        "expected": {
            "action": "goto_room",
            "room": 0,
        },
        "category": "navigation",
    },

    {
        "input": "Go to Room 1.",
        "expected": {
            "action": "goto_room",
            "room": 1,
        },
        "category": "navigation",
    },

    {
        "input": "Go to Room 2.",
        "expected": {
            "action": "goto_room",
            "room": 2,
        },
        "category": "navigation",
    },

    {
        "input": "Go to Room 3.",
        "expected": {
            "action": "goto_room",
            "room": 3,
        },
        "category": "navigation",
    },

    {
        "input": "Go to Room 4.",
        "expected": {
            "action": "goto_room",
            "room": 4,
        },
        "category": "navigation",
    },

    # ==================================================
    # B. Navigation paraphrases
    # ==================================================

    {
        "input": "Could you please go to room three?",
        "expected": {
            "action": "goto_room",
            "room": 3,
        },
        "category": "paraphrase",
    },

    {
        "input": "Head over to the third room.",
        "expected": {
            "action": "goto_room",
            "room": 3,
        },
        "category": "paraphrase",
    },

    {
        "input": "Please make your way to Room 2.",
        "expected": {
            "action": "goto_room",
            "room": 2,
        },
        "category": "paraphrase",
    },

    {
        "input": "Take me to the kitchen.",
        "expected": {
            "action": "goto_room",
            "room": 1,
        },
        "category": "paraphrase",
    },

    {
        "input": "Go over to Bedroom 3.",
        "expected": {
            "action": "goto_room",
            "room": 4,
        },
        "category": "paraphrase",
    },

    {
        "input": "Can you head to the living room?",
        "expected": {
            "action": "goto_room",
            "room": 0,
        },
        "category": "paraphrase",
    },

    # ==================================================
    # C. Other valid robot commands
    # ==================================================

    {
        "input": "What can you see?",
        "expected": {
            "action": "describe",
        },
        "category": "valid_other",
    },

    {
        "input": "Describe your surroundings.",
        "expected": {
            "action": "describe",
        },
        "category": "valid_other",
    },

    {
        "input": "Move closer to the red cup.",
        "expected": {
            "action": "approach",
            "object": "red cup",
        },
        "category": "valid_other",
    },

    {
        "input": "Approach the blue cylinder.",
        "expected": {
            "action": "approach",
            "object": "blue cylinder",
        },
        "category": "valid_other",
    },

    {
        "input": "Stop.",
        "expected": {
            "action": "stop",
        },
        "category": "valid_other",
    },

    # ==================================================
    # D. Invalid / unsupported requests
    # ==================================================

    {
        "input": "Go to Room 99.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Go to Room 7.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Go upstairs.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Leave the building.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Fly to the kitchen.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Open the front door.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Pick up the cup.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Turn on the television.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },

    {
        "input": "Make me a sandwich.",
        "expected": {
            "action": "chat",
        },
        "category": "invalid",
    },
]
