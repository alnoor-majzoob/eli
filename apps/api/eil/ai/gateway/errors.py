"""AI capability errors (plan §8)."""

from __future__ import annotations


class LLMError(RuntimeError):
    """Live LLM call failed (all retries exhausted or circuit breaker open)."""


class ReplayError(RuntimeError):
    """Replay mode: no cassette registered for the request hash."""
