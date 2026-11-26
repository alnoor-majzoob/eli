"""Connector registry + mode selection (plan §10, Phase 3, T3.4).

Modes: ``sim`` (simulator) or ``live``. Override with ``CONNECTOR_MODE_<SYSTEM>``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from connectors.sdk.mapping import MappingEngine
from connectors.sdk.protocol import (
    Connector,
    ConnectorCapabilities,
    ConnectorHealth,
    NotSupportedError,
    RawRecord,
)

BUILTIN_CONNECTORS: dict[str, type[Connector]] = {}


def register(cls: type[Connector]) -> type[Connector]:
    BUILTIN_CONNECTORS[cls.system] = cls
    return cls


def mode_for(system: str) -> str:
    override = os.environ.get(f"CONNECTOR_MODE_{system.upper()}")
    if override:
        return override
    cls = BUILTIN_CONNECTORS.get(system)
    return cls.default_mode if cls is not None else "sim"


def get_connector(system: str, mode: str | None = None) -> Connector:
    cls = BUILTIN_CONNECTORS.get(system)
    if cls is None:
        raise ValueError(f"Unknown connector system: {system}")
    return cls(mode or mode_for(system))


class BaseConnector:
    """Shared YAML-mapping + health plumbing for concrete connectors."""

    system: ClassVar[str]
    mapping_path: ClassVar[Path]
    default_mode: ClassVar[str] = "sim"

    def __init__(self, mode: str):
        self._mode = mode

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def engine(self) -> MappingEngine:
        engine = self.__dict__.get("_engine")
        if engine is None:
            engine = MappingEngine.load(self.mapping_path)
            self._engine = engine
        return engine

    def map_payload(self, raw: RawRecord) -> tuple[str, dict[str, Any]]:
        return raw.canonical_type, self.engine.apply(raw.canonical_type, raw.payload)

    def handle_webhook(self, payload: Any) -> list[RawRecord]:
        event = payload if isinstance(payload, dict) else {}
        record = event.get("record") or event.get("payload") or {}
        external_id = event.get("id") or event.get("record_id") or str(record.get("id") or uuid4())
        canonical_type = str(event.get("type") or record.get("type") or self.system)
        return [
            RawRecord(
                external_id=str(external_id),
                canonical_type=canonical_type,
                payload=record,
                is_simulated=True,
            )
        ]

    def push(self, change: dict[str, Any]) -> None:
        raise NotSupportedError(f"{self.system} connector does not support push")

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(
            status="ok", last_sync_at=None, lag_seconds=None, error_count=0
        )
