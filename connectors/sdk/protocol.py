"""Connector protocol (plan §10, Phase 3, T3.1)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol


@dataclass(frozen=True)
class RawRecord:
    """A record as pulled from a system of record, before canonical mapping."""

    external_id: str
    canonical_type: str
    payload: dict[str, Any]
    received_at: datetime | None = None
    is_simulated: bool = False


@dataclass(frozen=True)
class ConnectorCapabilities:
    system: str
    record_types: tuple[str, ...]
    modes: tuple[str, ...]
    default_mode: str
    push_supported: bool = False


@dataclass(frozen=True)
class ConnectorHealth:
    status: str
    last_sync_at: datetime | None
    lag_seconds: int | None
    error_count: int


class Connector(Protocol):
    """Contract every connector (and simulator-backed live adapter) implements."""

    system: ClassVar[str]
    mapping_path: ClassVar[Path]

    def capabilities(self) -> ConnectorCapabilities: ...
    def authenticate(self) -> None: ...
    def pull(self, since_cursor: str | None = None) -> Iterator[RawRecord]: ...
    def handle_webhook(self, payload: Any) -> list[RawRecord]: ...
    def push(self, change: dict[str, Any]) -> None:
        raise NotSupportedError(f"{self.system} connector does not support push")
    def health(self) -> ConnectorHealth: ...
    def map_payload(self, raw: RawRecord) -> tuple[str, dict[str, Any]]: ...


class NotSupportedError(RuntimeError):
    """Raised by skeleton connectors/modes without a live adapter."""
