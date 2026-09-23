"""Configuration names only; secret values are resolved at the request boundary."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit

DEFAULT_MODELS = {'openai': 'gpt-4o-mini', 'gemini': 'gemini-3.8-flash', 'qwen': 'qwen3-vl-flash'}
KEY_ENV = {'openai': 'OPENAI_API_KEY', 'gemini': 'GEMINI_API_KEY', 'qwen': 'DASHSCOPE_API_KEY'}


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    model: str
    key_env: str
    base_url: str


def resolve_config(provider, model=None, environ=None):
    env = os.environ if environ is None else environ
    if not provider:
        raise ValueError('MISSING_PROVIDER: select openai or gemini (qwen is deprecated for Task 3)')
    if provider not in DEFAULT_MODELS:
        raise ValueError('UNKNOWN_PROVIDER: select openai or gemini (qwen is deprecated for Task 3)')
    selected_model = DEFAULT_MODELS[provider] if model is None else model.strip()
    if not selected_model:
        raise ValueError('CONFIGURATION_ERROR: model must not be empty')
    url = 'https://api.openai.com/v1'
    if provider == 'gemini':
        url = 'https://generativelanguage.googleapis.com/v1beta/openai/'
    if provider == 'qwen':
        url = env.get('QWEN_BASE_URL', '').strip()
        if not url:
            raise ValueError('MISSING_QWEN_BASE_URL: set QWEN_BASE_URL explicitly')
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme == 'https' and parsed.hostname and
                     not parsed.username and not parsed.password and
                     not parsed.query and not parsed.fragment and
                     '{' not in url and '}' not in url)
            if not valid:
                raise ValueError()
        except ValueError:
            raise ValueError('INVALID_QWEN_BASE_URL: expected an explicit HTTPS base URL') from None
    return ProviderConfig(provider, selected_model, KEY_ENV[provider], url)
