"""Append-only local JSONL query audit with secret/header redaction."""
import json
import os
from pathlib import Path
import re
from threading import Lock


class QueryLog:
    def __init__(self, directory, environ=None):
        self.path = Path(directory).expanduser().resolve() / 'queries.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.environ = os.environ if environ is None else environ
        self.lock = Lock()

    def append(self, record):
        secrets = [self.environ.get(name, '').strip() for name in
                   ('OPENAI_API_KEY', 'GEMINI_API_KEY', 'DASHSCOPE_API_KEY')]
        def clean(value):
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()
                        if not any(word in key.lower() for word in ('authorization', 'api_key', 'headers'))}
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, str):
                for secret in secrets:
                    if secret:
                        value = value.replace(secret, '[REDACTED]')
                value = re.sub(r'(?im)(?:authorization|(?:[a-z_]*api[_ -]?key))\s*[:=][^\r\n]*',
                               '[REDACTED]', value)
                value = re.sub(r'(?i)\b(?:Bearer|Basic)\s+\S+', '[REDACTED]', value)
            return value
        line = json.dumps(clean(record), ensure_ascii=False, allow_nan=False) + '\n'
        with self.lock:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, 'a', encoding='utf-8') as stream:
                stream.write(line)
