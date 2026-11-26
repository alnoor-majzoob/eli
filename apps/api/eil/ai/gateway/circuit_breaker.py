"""Circuit breaker (plan §8.4): open after N consecutive failures, route to fallback."""

from __future__ import annotations

import time


class CircuitBreaker:
    def __init__(self, threshold: int = 3, cooldown_seconds: float = 30.0):
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = time.monotonic()

    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self._cooldown:
            self._failures = 0
            self._opened_at = None
            return False
        return True
