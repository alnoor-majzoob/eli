"""Shared simulator helpers: in-memory event store + webhook push (plan §10, T3.3)."""

from __future__ import annotations

import json
import threading
import urllib.request
from datetime import UTC, datetime
from typing import Any


class EventStore:
    """In-memory event store; events carry sequential ids used as cursors."""

    def __init__(self, seed: list[dict[str, Any]]):
        self._events: list[dict[str, Any]] = []
        self._targets: list[str] = []
        self._counter = 0
        self._lock = threading.Lock()
        for record in seed:
            self.inject(record)

    def _next_id(self) -> str:
        self._counter += 1
        return f"e{self._counter:04d}"

    def inject(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            event_id = self._next_id()
            event = {
                "id": event_id,
                "type": record.get("type"),
                "record": record,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._events.append(event)
        self._push(event)
        return event

    def list_events(self, after: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            events = [dict(event) for event in self._events]
        return [event for event in events if after is None or event["id"] > after]

    def add_target(self, url: str) -> None:
        with self._lock:
            if url not in self._targets:
                self._targets.append(url)

    def targets(self) -> list[str]:
        with self._lock:
            return list(self._targets)

    def _push(self, event: dict[str, Any]) -> None:
        for target in self._targets:
            try:
                request = urllib.request.Request(
                    target,
                    data=json.dumps(event).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(request, timeout=2).read()
            except Exception:  # noqa: BLE001 - best-effort webhook push
                pass
