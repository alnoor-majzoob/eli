"""Canonical-record ingestion: map canonical records to the work graph.

Flow per record (plan §10, Phase 3, T3.2 + T3.6 reconciliation):
1. Connector maps the raw record to a canonical type + payload (YAML mapping).
2. Validate external artifact URLs against SSRF rules (plan §13.3, Phase 9, T9.2).
3. Find the existing ``work_item`` by the ``external_ref`` binding
   (system + external_id); none found → create a new external work item.
4. Reconcile: the system-of-record wins on ``external_ref.owned_fields``;
   changes to non-owned fields are logged as ``SyncConflict`` rows.
5. Persist the raw record as a ``SourceArtifact`` and bind/update the
   ``ExternalRef`` (``last_synced_at``, ``content_hash``, ``is_simulated``).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

import structlog
from connectors.sdk.protocol import RawRecord
from connectors.sdk.urls import URLValidationError, validate_connector_url
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.graph.cache import graph_cache
from eil.modules.integration.models import (
    ApprovedSource,
    ExternalRef,
    SourceArtifact,
    SyncConflict,
)

logger = structlog.get_logger(__name__)

CANONICAL_TO_WORK_TYPE: dict[str, WorkType] = {
    "project": WorkType.PROJECT,
    "activity": WorkType.TASK,
    "milestone": WorkType.MILESTONE,
    "work_order": WorkType.TASK,
}

SIM_SYSTEMS = frozenset({"p6", "eam", "erp", "hr", "m365"})


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _safe_external_url(url: Any, source: ApprovedSource) -> str | None:
    """Validate a connector-supplied URL against SSRF rules (plan §13.3, T9.2).

    Sim systems run on the local/LAN network by design; live-source URLs must
    be public https. Unsafe URLs are dropped (``None``) with a warning — the
    record itself is still ingested.
    """
    if not url or not isinstance(url, str):
        return None
    try:
        validated: str = validate_connector_url(
            url,
            allow_private=source.type in SIM_SYSTEMS,
            require_https=source.type not in SIM_SYSTEMS,
        )
    except URLValidationError as exc:
        logger.warning("external_url_rejected", error=str(exc), url_length=len(url))
        return None
    return validated


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _compare_value(old: Any, new: Any) -> bool:
    return bool(_json_safe(old) != _json_safe(new))


async def _find_ref(session: AsyncSession, system: str, external_id: str) -> ExternalRef | None:
    return (
        await session.execute(
            select(ExternalRef).where(
                ExternalRef.system == system,
                ExternalRef.external_id == external_id,
            )
        )
    ).scalar_one_or_none()


async def _store_artifact(
    session: AsyncSession,
    source: ApprovedSource,
    external_id: str,
    canonical_type: str,
    payload: dict[str, Any],
    *,
    received_at: datetime | None,
    uri: str | None,
    title: str | None,
) -> SourceArtifact | None:
    existing = (
        await session.execute(
            select(SourceArtifact).where(
                SourceArtifact.source_id == source.id,
                SourceArtifact.external_id == external_id,
            )
        )
    ).scalar_one_or_none()
    content_hash = _payload_hash(payload)
    if existing is not None and existing.content_hash == content_hash:
        return None
    if existing is None:
        artifact = SourceArtifact(
            source_id=source.id,
            kind=canonical_type,
            external_id=external_id,
            uri=uri,
            title=title,
            occurred_at=received_at,
            participants=[],
            payload=payload,
            content_hash=content_hash,
            classification=source.classification,
            ai_processing_allowed=source.ai_processing_allowed,
            language="en",
        )
        session.add(artifact)
        await session.flush()
        return artifact
    existing.kind = canonical_type
    existing.uri = uri or existing.uri
    existing.title = title or existing.title
    existing.occurred_at = received_at or existing.occurred_at
    existing.payload = payload
    existing.content_hash = content_hash
    return existing


_RECONCILE_FIELDS = (
    "title",
    "description",
    "status",
    "planned_start",
    "planned_end",
)


async def upsert_record(
    session: AsyncSession,
    source: ApprovedSource,
    connector: Any,
    raw: RawRecord,
) -> WorkItem | None:
    """Create or reconcile one canonical record from a system of record."""
    canonical_type, payload = connector.map_payload(raw)
    safe_payload = {key: _json_safe(value) for key, value in payload.items()}
    external_url = _safe_external_url(payload.get("uri") or payload.get("url"), source)

    await _store_artifact(
        session,
        source,
        raw.external_id,
        canonical_type,
        safe_payload,
        received_at=raw.received_at or datetime.now(UTC),
        uri=external_url,
        title=payload.get("title") or payload.get("name"),
    )

    work_type = CANONICAL_TO_WORK_TYPE.get(canonical_type)
    if work_type is None:
        # Person / certification / meeting / document — artifact only.
        await session.commit()
        return None

    title = (
        payload.get("title")
        or payload.get("name")
        or payload.get("work_order_number")
        or f"{canonical_type}: {raw.external_id}"
    )
    external_changes = {
        "title": title,
        "description": payload.get("description"),
        "status": payload.get("status"),
        "planned_start": payload.get("planned_start") or payload.get("start_date"),
        "planned_end": payload.get("planned_end") or payload.get("end_date"),
    }

    ref = await _find_ref(session, source.type, raw.external_id)
    if ref is None:
        item = WorkItem(
            type=work_type.value,
            title=title,
            description=payload.get("description"),
            status="active",
            origin="external",
            attributes={
                "canonical_type": canonical_type,
                "external_id": raw.external_id,
                "source_type": source.type,
                "canonical": safe_payload,
            },
            planned_start=payload.get("planned_start") or payload.get("start_date"),
            planned_end=payload.get("planned_end") or payload.get("end_date"),
        )
        session.add(item)
        await session.flush()
        ref = ExternalRef(
            work_item_id=item.id,
            system=source.type,
            external_id=raw.external_id,
            external_url=external_url,
            owned_fields=source.owned_fields or ["*"],
            is_simulated=raw.is_simulated or source.type in SIM_SYSTEMS,
            content_hash=_payload_hash(payload),
            last_synced_at=datetime.now(UTC),
        )
        session.add(ref)
        await session.commit()
        graph_cache.invalidate()
        return item

    # Reconcile against the existing binding (plan §13.2, SOD-4): the
    # system-of-record wins on owned fields; others log conflicts.
    existing = (
        await session.execute(select(WorkItem).where(WorkItem.id == ref.work_item_id))
    ).scalar_one_or_none()
    if existing is None:
        await session.delete(ref)
        await session.commit()
        return None

    owned = set(ref.owned_fields or ["*"])
    for field in _RECONCILE_FIELDS:
        new_value = external_changes[field]
        if new_value is None:
            continue
        old_value = getattr(existing, field)
        if not _compare_value(old_value, new_value):
            continue
        if owned & {"*", field}:
            setattr(existing, field, new_value)
        else:
            session.add(
                SyncConflict(
                    source_id=source.id,
                    work_item_id=existing.id,
                    field=field,
                    external_value={"value": _json_safe(new_value)},
                    local_value={"value": _json_safe(old_value)},
                    description=(
                        f"External update to {field} ignored: field not owned by '{source.type}'."
                    ),
                )
            )
    existing.updated_at = datetime.now(UTC)
    existing.version += 1
    ref.content_hash = _payload_hash(payload)
    ref.last_synced_at = datetime.now(UTC)
    ref.is_simulated = raw.is_simulated or source.type in SIM_SYSTEMS
    session.add(ref)
    await session.commit()
    graph_cache.invalidate()
    return existing
