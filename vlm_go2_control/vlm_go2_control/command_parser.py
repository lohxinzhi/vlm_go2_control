"""Natural-language command parser for the Unitree Go2 robot."""

import json
import os

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
- Do not write text before or after the JSON object.
- Valid room numbers are 0, 1, 2, 3, and 4.
- Never invent a room.
- Invalid room requests must use "chat".
- Unclear requests must use "chat" and ask for clarification.
- Questions about what the robot can see must use "describe".
- Requests to approach or move toward an object must use "approach".
- Requests to stop the robot must use "stop".
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
    """Convert natural-language requests into validated robot commands."""

    def __init__(self, use_mock=False):
        """Initialize the parser."""

        self.use_mock = use_mock
        self.history = []

        if not self.use_mock:
            api_key = os.environ.get("OPENAI_API_KEY")

            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. "
                    "Set the API key or use mock mode."
                )

            self.client = OpenAI(
                api_key=api_key
            )

            self.model = "gpt-5-mini"

    def parse(self, user_text):
        """Convert one user message into a validated command."""

        if self.use_mock:
            command = self.mock_parse(
                user_text
            )

        else:
            command = self.call_llm(
                user_text
            )

        command = self.validate_command(
            command
        )

        self.add_to_history(
            user_text,
            command,
        )

        return command

    def call_llm(self, user_text):
        """Send a user message to the LLM."""

        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        messages.extend(
            self.history
        )

        messages.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        for attempt in range(2):

            try:
                response = (
                    self.client
                    .chat
                    .completions
                    .create(
                        model=self.model,
                        messages=messages,
                    )
                )

                raw_response = (
                    response
                    .choices[0]
                    .message
                    .content
                )

                command = json.loads(
                    raw_response
                )

                return command

            except json.JSONDecodeError:

                if attempt == 0:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was not "
                                "valid JSON. Return ONLY one "
                                "valid JSON object."
                            ),
                        }
                    )

                    continue

                return {
                    "action": "chat",
                    "reply": (
                        "I could not understand that command. "
                        "Please try again."
                    ),
                }

            except Exception as error:

                print(
                    "LLM error:",
                    error,
                )

                return {
                    "action": "chat",
                    "reply": (
                        "The language model is currently "
                        "unavailable."
                    ),
                }

        return {
            "action": "chat",
            "reply": "I could not understand that command.",
        }

    def validate_command(self, command):
        """Validate a command before allowing robot execution."""

        if not isinstance(command, dict):
            return {
                "action": "chat",
                "reply": "The command format was invalid.",
            }

        action = command.get(
            "action"
        )

        if action not in VALID_ACTIONS:
            return {
                "action": "chat",
                "reply": "That action is not supported.",
            }

        if action == "goto_room":

            room = command.get(
                "room"
            )

            try:
                room = int(room)

            except (
                TypeError,
                ValueError,
            ):
                return {
                    "action": "chat",
                    "reply": (
                        "Please specify a valid "
                        "room number."
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

            object_name = command.get(
                "object"
            )

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
                "object": str(
                    object_name
                ),
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

    def add_to_history(
        self,
        user_text,
        command,
    ):
        """Store one conversation turn."""

        self.history.append(
            {
                "role": "user",
                "content": user_text,
            }
        )

        self.history.append(
            {
                "role": "assistant",
                "content": json.dumps(
                    command
                ),
            }
        )

        self.trim_history()

    def trim_history(self):
        """Keep only recent conversation history."""

        max_history_messages = 10

        if len(
            self.history
        ) > max_history_messages:

            self.history = self.history[
                -max_history_messages:
            ]

    def clear_history(self):
        """Clear all stored conversation history."""

        self.history.clear()

    def mock_parse(self, user_text):
        """Offline parser used only for development and testing."""

        text = (
            user_text
            .lower()
            .strip()
        )

        room_words = {
            "room 0": 0,
            "room zero": 0,
            "living room": 0,

            "room 1": 1,
            "room one": 1,
            "first room": 1,
            "kitchen": 1,

            "room 2": 2,
            "room two": 2,
            "second room": 2,
            "bedroom 1": 2,

            "room 3": 3,
            "room three": 3,
            "third room": 3,
            "bedroom 2": 3,

            "room 4": 4,
            "room four": 4,
            "fourth room": 4,
            "bedroom 3": 4,
        }

        if "room 99" in text:
            return {
                "action": "chat",
                "reply": "Room 99 is not available.",
            }

        for phrase, room_id in room_words.items():

            if phrase in text:
                return {
                    "action": "goto_room",
                    "room": room_id,
                }

        if (
            "what can you see" in text
            or "describe" in text
            or "surroundings" in text
        ):
            return {
                "action": "describe",
            }

        if (
            "approach" in text
            or "move closer" in text
        ):

            object_name = "object"

            if "red cup" in text:
                object_name = "red cup"

            elif "blue cylinder" in text:
                object_name = "blue cylinder"

            return {
                "action": "approach",
                "object": object_name,
            }

        if "stop" in text:
            return {
                "action": "stop",
            }

        return {
            "action": "chat",
            "reply": (
                "I cannot perform that request."
            ),
        }
