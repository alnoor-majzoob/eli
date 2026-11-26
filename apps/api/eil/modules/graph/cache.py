"""TTL cache for graph read responses with event-based invalidation.

Graph endpoints call :meth:`invalidate` when graph-structure events happen
(work link created/deleted, work item created/updated/deleted), so cached
responses cannot go stale within the TTL window.
"""

from __future__ import annotations

import time
from typing import Any

DEFAULT_TTL_SECONDS = 30.0


class _GraphCache:
    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._entries: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._entries.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._entries[key] = (time.monotonic() + (self._ttl if ttl is None else ttl), value)

    def invalidate(self) -> None:
        self._entries.clear()


graph_cache = _GraphCache()
