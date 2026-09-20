"""Shared Chat Completions transport; imports the SDK only for enabled requests."""
from typing import Protocol
import math
import json
import logging
import socket
import ssl
import os
import time
from ..types import QueryOptions, VLMResult
from ..image_encoding import PreparedImage
from .config import ProviderConfig


LOGGER = logging.getLogger(__name__)
TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
RETRY_DELAYS = (2, 4)


def retry_classification(exc):
    """Return only numeric status, fixed category and retry decision; no raw text."""
    status = getattr(exc, 'status_code', None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    if status is not None:
        retry = status in TRANSIENT_HTTP_STATUSES
        return status, 'TRANSIENT_HTTP_ERROR' if retry else 'PERMANENT_HTTP_ERROR', retry
    causes, current = [], exc
    while current is not None and len(causes) < 8 and all(current is not c for c in causes):
        causes.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(c, ssl.SSLError) for c in causes):
        return None, 'TLS_ERROR', False
    if any(isinstance(c, socket.gaierror) and c.errno != socket.EAI_AGAIN for c in causes):
        return None, 'PERMANENT_DNS_ERROR', False
    # Lazy imports preserve disabled/no-credential operation without an SDK.
    import httpx
    import openai
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException, TimeoutError)):
        return None, 'TIMEOUT', True
    if isinstance(exc, (openai.APIConnectionError, httpx.NetworkError, ConnectionError)):
        return None, 'CONNECTION_ERROR', True
    if isinstance(exc, socket.gaierror) and exc.errno == socket.EAI_AGAIN:
        return None, 'TEMPORARY_DNS_ERROR', True
    return None, 'PERMANENT_ERROR', False


class SceneProvider(Protocol):
    def query(self, image: PreparedImage, prompt: str, options: QueryOptions) -> VLMResult: ...


def _usage_numbers(value):
    # Usage is numeric metadata, never response text, headers, or credentials.
    if isinstance(value, dict):
        return {k: _usage_numbers(v) for k, v in value.items()
                if isinstance(v, (dict, int, float)) or v is None}
    return value


def normalize_response(response, provider, model):
    result = VLMResult(provider=provider, model=model)
    usage = getattr(response, 'usage', None)
    if usage is not None:
        raw = usage if isinstance(usage, dict) else usage.model_dump()
        result.raw_usage = _usage_numbers(raw)
        for target, source in [('input_tokens', 'prompt_tokens'),
                               ('output_tokens', 'completion_tokens'),
                               ('total_tokens', 'total_tokens')]:
            value = raw.get(source)
            if type(value) is int and value >= 0:
                setattr(result, target, value)
    choices = getattr(response, 'choices', [])
    answer = getattr(getattr(choices[0], 'message', None), 'content', None) if choices else None
    if not isinstance(answer, str) or not answer.strip():
        result.error_type = 'INVALID_RESPONSE'
        result.error_message = 'Provider returned no textual answer'
        return result
    result.success = True
    result.answer = answer.strip()
    return result


class ChatCompletionsProvider:
    def __init__(self, config: ProviderConfig, client_factory=None, environ=None):
        self.config = config
        self._client_factory = client_factory
        self._environ = environ

    def handle_error(self, result, exc):
        result.error_type = 'PROVIDER_ERROR'
        result.error_message = 'Provider request failed; response details are not logged'

    def query(self, image, prompt, options):
        start = time.monotonic()
        result = VLMResult(provider=self.config.provider, model=self.config.model)
        attempts = []
        try:
            if not options.enable_external_api_calls:
                result.error_type = 'EXTERNAL_API_DISABLED'
                result.error_message = 'External API calls are disabled'
                return result
            if (not math.isfinite(options.timeout_sec) or options.timeout_sec <= 0 or
                    type(options.max_output_tokens) is not int or options.max_output_tokens < 1):
                result.error_type = 'INVALID_OPTIONS'
                result.error_message = 'Positive timeout and output-token limit required'
                return result
            env = os.environ if self._environ is None else self._environ
            key = env.get(self.config.key_env, '').strip()
            if not key:
                result.error_type = 'MISSING_API_KEY'
                result.error_message = f'Set {self.config.key_env} in the node environment'
                return result
            factory = self._client_factory
            if factory is None:
                try:
                    from openai import OpenAI
                except ImportError:
                    result.error_type = 'MISSING_DEPENDENCY'
                    result.error_message = 'The Python openai distribution is not installed'
                    return result
                factory = OpenAI
            # Encode once; all attempts use the identical semantic request.
            payload = dict(model=self.config.model,
                messages=[{'role': 'user', 'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': image.data_uri()}},
                ]}], max_tokens=options.max_output_tokens, stream=False)
            # SDK retries stay disabled so this loop owns the total attempt bound.
            with factory(api_key=key, base_url=self.config.base_url,
                         timeout=options.timeout_sec, max_retries=0) as client:
                for attempt in range(1, 4):
                    attempt_start = time.monotonic()
                    status, category, retry = None, 'SUCCESS', False
                    try:
                        response = client.chat.completions.create(**payload)
                    except Exception as exc:
                        status, category, retry = retry_classification(exc)
                        if not retry or attempt == 3:
                            self.handle_error(result, exc)
                    else:
                        result = normalize_response(response, self.config.provider, self.config.model)
                        category = 'SUCCESS' if result.success else result.error_type
                    record = {'attempt': attempt, 'http_status': status, 'category': category,
                              'latency_sec': time.monotonic() - attempt_start,
                              'total_elapsed_sec': time.monotonic() - start}
                    attempts.append(record)
                    LOGGER.info('VLM attempt %s', json.dumps(record, sort_keys=True))
                    if not retry or attempt == 3:
                        break
                    time.sleep(RETRY_DELAYS[attempt - 1])
        except Exception as exc:
            self.handle_error(result, exc)
        finally:
            result.latency_sec = time.monotonic() - start
            result.metadata['attempts'] = attempts
            if attempts:
                LOGGER.info('VLM total_elapsed_sec=%s attempts=%s', result.latency_sec, len(attempts))
        return result
