"""ROS-independent provider result and request options."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueryOptions:
    enable_external_api_calls: bool = False
    jpeg_quality: int = 90
    max_output_tokens: int = 256
    timeout_sec: float = 30.0


@dataclass
class VLMResult:
    success: bool = False
    answer: str = ''
    provider: str = ''
    model: str = ''
    latency_sec: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    raw_usage: dict[str, Any] = field(default_factory=dict)
    error_type: str = ''
    error_message: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
