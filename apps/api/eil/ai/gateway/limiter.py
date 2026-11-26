"""Per-alias token bucket (plan §8.4)."""

from __future__ import annotations

import asyncio
import time


class TokenBucket:
    def __init__(self, rate_per_min: float, capacity: int):
        self._rate = float(rate_per_min) / 60.0
        self._capacity = float(capacity)
        self._tokens = self._capacity
        self._last = time.monotonic()

    async def acquire(self, tokens: float = 1.0) -> None:
        while True:
            now = time.monotonic()
            self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
            self._last = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            await asyncio.sleep((tokens - self._tokens) / self._rate)
