from .config import resolve_config
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider
from .qwen_provider import QwenProvider


def create_provider(provider, model=None, *, environ=None, client_factory=None):
    config = resolve_config(provider, model, environ)
    cls = {'openai': OpenAIProvider, 'gemini': GeminiProvider, 'qwen': QwenProvider}[config.provider]
    return cls(config, client_factory=client_factory, environ=environ)
