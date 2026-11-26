"""LLM client protocol (plan §8.1) — public exports of the gateway package."""

from __future__ import annotations

from eil.ai.gateway.base import ChatResult, LLMCapabilities, LLMClient
from eil.ai.gateway.cache import ResponseCache
from eil.ai.gateway.circuit_breaker import CircuitBreaker
from eil.ai.gateway.client import GroqClient
from eil.ai.gateway.errors import LLMError, ReplayError
from eil.ai.gateway.gateway import Gateway, get_gateway
from eil.ai.gateway.limiter import TokenBucket
from eil.ai.gateway.replay import ReplayClient
from eil.ai.gateway.telemetry import hash_request, record_llm_call

__all__ = [
    "ChatResult",
    "CircuitBreaker",
    "Gateway",
    "GroqClient",
    "LLMCapabilities",
    "LLMClient",
    "LLMError",
    "ReplayClient",
    "ReplayError",
    "ResponseCache",
    "TokenBucket",
    "get_gateway",
    "hash_request",
    "record_llm_call",
]
