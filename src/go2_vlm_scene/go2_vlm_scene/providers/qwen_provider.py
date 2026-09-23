"""Qwen-only, allowlisted error diagnostics; never serialize raw SDK exceptions."""
import json
import os
import re
import socket
import ssl

from .base import ChatCompletionsProvider


# Unknown provider codes are omitted rather than echoing arbitrary response text.
SAFE_CODES = frozenset({
    'InvalidApiKey', 'InvalidApiKeyError', 'InvalidParameter', 'InvalidParameterValue',
    'AccessDenied', 'Forbidden', 'Unauthorized', 'ModelNotFound', 'NotFound',
    'InvalidURL', 'InvalidWorkspace', 'WorkspaceNotFound', 'PermissionDenied',
    'Throttling', 'Throttling.RateQuota', 'Throttling.AllocationQuota',
    'QuotaExceeded', 'AllocationQuota.FreeTierOnly', 'InsufficientBalance',
    'Arrearage', 'ServiceUnavailable', 'InternalError', 'DataInspectionFailed',
    'invalid_api_key', 'model_not_found', 'insufficient_quota', 'rate_limit_exceeded',
})
HTTP_MESSAGES = {
    401: ('AUTHENTICATION_ERROR', 'Authentication failed; check API key validity and region/workspace association.'),
    403: ('ACCESS_DENIED', 'Access denied; check workspace and model permissions.'),
    404: ('NOT_FOUND', 'Resource not found; check workspace, model and endpoint.'),
    429: ('RATE_OR_QUOTA_LIMIT', 'Rate or quota limit; check quota, balance and rate limits.'),
}


def safe_diagnostics(exc, environ):
    # Credential values are used only to reject candidate fields, never output.
    secrets = [environ.get(k, '').strip() for k in
               ('DASHSCOPE_API_KEY', 'OPENAI_API_KEY', 'QWEN_BASE_URL')]
    def clean_identifier(value, pattern):
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            return None
        if any(secret and secret in value for secret in secrets):
            return None
        return value

    status = getattr(exc, 'status_code', None)
    status = status if type(status) is int and 100 <= status <= 599 else None
    category, message = HTTP_MESSAGES.get(
        status, ('HTTP_ERROR' if status else 'PROVIDER_ERROR',
                 'Provider returned an HTTP error.' if status else 'Provider failed; raw error details withheld.'))
    # Inspect types, not cause messages, URLs or request contents.
    causes, current = [], exc
    for _ in range(8):
        if current is None or any(current is item for item in causes):
            break
        causes.append(current)
        current = current.__cause__ or current.__context__
    classes = {type(item).__name__ for item in causes}
    if status is None:
        if any(isinstance(item, socket.gaierror) for item in causes):
            category, message = 'DNS_ERROR', 'DNS resolution failed.'
        elif any(isinstance(item, ssl.SSLError) for item in causes):
            category, message = 'TLS_ERROR', 'TLS connection or certificate validation failed.'
        elif classes & {'APITimeoutError', 'TimeoutException', 'ConnectTimeout', 'ReadTimeout', 'WriteTimeout', 'PoolTimeout'}:
            category, message = 'TIMEOUT', 'Provider connection or response timed out.'
        elif classes & {'APIConnectionError', 'ConnectError', 'ConnectionError', 'NetworkError'}:
            category, message = 'CONNECTION_ERROR', 'Connection failed; DNS/TLS details may be unavailable.'
    body = getattr(exc, 'body', None)
    body = body if isinstance(body, dict) else {}
    nested = body.get('error')
    error = nested if isinstance(nested, dict) else body
    code = error.get('code')
    code = code if isinstance(code, str) and code in SAFE_CODES else None
    if code and any(secret and secret in code for secret in secrets):
        code = None
    # Only read the request-ID header; never iterate or serialize headers.
    response = getattr(exc, 'response', None)
    headers = getattr(response, 'headers', {})
    request_id = (body.get('request_id') or error.get('request_id')
                  or headers.get('x-request-id') or headers.get('x-acs-request-id'))
    request_id = clean_identifier(
        request_id, r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})')
    return {
        'http_status': status, 'alibaba_error_code': code,
        'sanitized_message': message, 'request_id': request_id,
        'exception_class': clean_identifier(type(exc).__name__, r'[A-Za-z][A-Za-z0-9_]{0,79}'),
        'category': category,
    }


class QwenProvider(ChatCompletionsProvider):
    """Model Studio adapter with safe structured diagnostics in error_message."""

    def handle_error(self, result, exc):
        env = os.environ if self._environ is None else self._environ
        try:
            diagnostics = safe_diagnostics(exc, env)
        except Exception:
            diagnostics = {'category': 'PROVIDER_ERROR',
                           'sanitized_message': 'Diagnostic extraction failed; raw details withheld.'}
        result.error_type = 'PROVIDER_ERROR'
        # Existing result/ROS/metadata paths already persist error_message.
        result.error_message = json.dumps(diagnostics, sort_keys=True)
