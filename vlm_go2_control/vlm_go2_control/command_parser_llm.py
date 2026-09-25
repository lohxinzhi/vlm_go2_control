"""LLM-based natural-language command parser for the Go2 robot."""

import json

from openai import OpenAI


SYSTEM_PROMPT = """
You are the command parser for an indoor Unitree Go2 robot.

Convert each user request into exactly one JSON object.

The robot knows these rooms:

Room 0: Living Room
Room 1: Kitchen
Room 2: Bedroom 1
Room 3: Bedroom 2
Room 4: Bedroom 3

Allowed commands:

1. Navigate to a room:
{"action": "goto_room", "room": <room number>}

2. Describe the surroundings:
{"action": "describe"}

3. Approach an object:
{"action": "approach", "object": "<object name>"}

4. Stop:
{"action": "stop"}

5. Normal conversation, invalid commands, unsupported requests,
or requests requiring clarification:
{"action": "chat", "reply": "<short response>"}

Rules:

- Return ONLY one valid JSON object.
- Do not use Markdown.
- Do not write text outside the JSON object.
- Valid rooms are Room 0, Room 1, Room 2, Room 3, and Room 4.
- Never invent a room.
- Invalid room requests must use the "chat" action.
- Unclear requests must use "chat" and ask for clarification.
- Questions about what the robot can see should use "describe".
- Requests to approach or move toward an object should use "approach".
- Requests to stop should use "stop".
"""


VALID_ACTIONS = {
    "goto_room",
    "describe",
    "approach",
    "stop",
    "chat",
}


VALID_ROOMS = {
    0,
    1,
    2,
    3,
    4,
}


class CommandParser:
    """Convert natural-language requests into validated commands."""

    def __init__(self):
        """Create the OpenAI client and conversation history."""

        self.client = OpenAI()

        self.model = "gpt-5-mini"

        self.history = []

    def parse(self, user_text):
        """Parse one user message."""

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        messages.extend(self.history)

        messages.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )

            raw_response = (
                response
                .choices[0]
                .message
                .content
            )

            command = json.loads(raw_response)

        except json.JSONDecodeError:
            return {
                "action": "chat",
                "reply": (
                    "I could not understand that command. "
                    "Please try again."
                ),
            }

        except Exception as error:
            print("LLM error:", error)

            return {
                "action": "chat",
                "reply": (
                    "The language model is currently unavailable."
                ),
            }

        command = self.validate_command(command)

        self.history.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        self.history.append(
            {
                "role": "assistant",
                "content": json.dumps(command),
            }
        )

        self.trim_history()

        return command

    def validate_command(self, command):
        """Validate an LLM command before robot execution."""

        if not isinstance(command, dict):
            return {
                "action": "chat",
                "reply": "The command format was invalid.",
            }

        action = command.get("action")

        if action not in VALID_ACTIONS:
            return {
                "action": "chat",
                "reply": "That action is not supported.",
            }

        if action == "goto_room":
            room = command.get("room")

            try:
                room = int(room)

            except (TypeError, ValueError):
                return {
                    "action": "chat",
                    "reply": (
                        "Please specify a valid room number."
                    ),
                }

            if room not in VALID_ROOMS:
                return {
                    "action": "chat",
                    "reply": (
                        f"Room {room} is not available. "
                        "Please choose Room 0 to Room 4."
                    ),
                }

            return {
                "action": "goto_room",
                "room": room,
            }

        if action == "describe":
            return {
                "action": "describe",
            }

        if action == "approach":
            object_name = command.get("object")

            if not object_name:
                return {
                    "action": "chat",
                    "reply": (
                        "Please tell me which object "
                        "you want me to approach."
                    ),
                }

            return {
                "action": "approach",
                "object": str(object_name),
            }

        if action == "stop":
            return {
                "action": "stop",
            }

        return {
            "action": "chat",
            "reply": command.get(
                "reply",
                "I am not sure what you mean.",
            ),
        }

    def trim_history(self):
        """Keep only recent conversation history."""

        max_history_messages = 10

        if len(self.history) > max_history_messages:
            self.history = self.history[
                -max_history_messages:
            ]
