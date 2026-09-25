"""Parse user text into structured robot commands."""


def parse_command(text):
    """Convert simple text commands into robot actions."""

    text = text.lower().strip()

    if "room 0" in text:
        return {
            "action": "goto_room",
            "room": 0,
        }

    if "room 1" in text:
        return {
            "action": "goto_room",
            "room": 1,
        }

    if "room 2" in text:
        return {
            "action": "goto_room",
            "room": 2,
        }

    if "room 3" in text:
        return {
            "action": "goto_room",
            "room": 3,
        }

    if "room 4" in text:
        return {
            "action": "goto_room",
            "room": 4,
        }

    if "describe" in text or "what can you see" in text:
        return {
            "action": "describe",
        }

    if "stop" in text:
        return {
            "action": "stop",
        }

    return {
        "action": "chat",
        "reply": "I did not understand that command.",
    }
