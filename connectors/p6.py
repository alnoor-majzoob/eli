"""Primavera P6 connector — simulator (plan §10, Phase 3, T3.3).

Live-mode adapter is a skeleton (plan §10, T3.4): sim mode pulls activities and
milestones from ``p6-sim`` (``GET /events?after=`` cursor).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from connectors.sdk.protocol import ConnectorCapabilities, RawRecord
from connectors.sdk.registry import BaseConnector, register
from connectors.sdk.sim import fetch_events, post_event, sim_base


@register
class P6Connector(BaseConnector):
    system = "p6"
    mapping_path = Path(__file__).parent / "mappings" / "p6.yaml"
    default_mode = "sim"

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            system="p6",
            record_types=("activity", "milestone"),
            modes=("sim",),
            default_mode="sim",
            push_supported=True,
        )

    def authenticate(self) -> None:
        if self._mode == "live":
            raise NotImplementedError("live P6 adapter is a skeleton (plan §10, T3.4)")

    def pull(self, since_cursor: str | None = None) -> Iterator[RawRecord]:
        if self._mode == "live":
            raise NotImplementedError("live P6 adapter is a skeleton (plan §10, T3.4)")
        for event in fetch_events(sim_base("p6"), since_cursor):
            yield RawRecord(
                external_id=str(event["id"]),
                canonical_type=str(event.get("type") or "activity"),
                payload=event.get("record") or {},
                is_simulated=True,
            )

    def push(self, change: dict[str, Any]) -> None:
        if self._mode == "live":
            raise NotImplementedError("live P6 adapter is a skeleton (plan §10, T3.4)")
        record = {"type": change.get("action", "activity"), **(change.get("payload") or {})}
        post_event(sim_base("p6"), record)
