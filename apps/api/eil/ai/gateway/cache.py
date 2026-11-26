"""Response cache keyed by request hash (plan §8.4)."""

from __future__ import annotations

import time


class ResponseCache:
    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: str, content: str, ttl: float | None = None) -> None:
        self._entries[key] = (time.monotonic() + (self._ttl if ttl is None else ttl), content)

    def invalidate(self) -> None:
        self._entries.clear()
