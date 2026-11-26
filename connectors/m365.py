"""Microsoft 365 connector — Graph-shaped (plan §10, Phase 3, T3.3/T4).

Sim mode pulls meetings, messages and documents from ``m365-sim``
(``GET /events?after=`` cursor); live mode raises until the tenant-registered
Graph client is wired (plan §10, T3.4).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from connectors.sdk.protocol import ConnectorCapabilities, ConnectorHealth, RawRecord
from connectors.sdk.registry import BaseConnector, register
from connectors.sdk.sim import fetch_events, post_event, sim_base


@register
class M365Connector(BaseConnector):
    system = "m365"
    mapping_path = Path(__file__).parent / "mappings" / "m365.yaml"
    default_mode = "sim"

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            system="m365",
            record_types=("meeting", "message", "document"),
            modes=("sim",),
            default_mode="sim",
            push_supported=True,
        )

    def authenticate(self) -> None:
        if self._mode == "live":
            raise NotImplementedError("live M365 Graph adapter pending (plan §10, T3.4)")

    def pull(self, since_cursor: str | None = None) -> Iterator[RawRecord]:
        if self._mode == "live":
            raise NotImplementedError("live M365 Graph adapter pending (plan §10, T3.4)")
        for event in fetch_events(sim_base("m365"), since_cursor):
            yield RawRecord(
                external_id=str(event["id"]),
                canonical_type=str(event.get("type") or "message"),
                payload=event.get("record") or {},
                is_simulated=True,
            )

    def push(self, change: dict[str, Any]) -> None:
        if self._mode == "live":
            raise NotImplementedError("live M365 Graph adapter pending (plan §10, T3.4)")
        record = {"type": change.get("action", "message"), **(change.get("payload") or {})}
        post_event(sim_base("m365"), record)

    def health(self) -> ConnectorHealth:
        return ConnectorHealth(status="ok", last_sync_at=None, lag_seconds=None, error_count=0)
