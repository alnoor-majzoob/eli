"""Sync orchestration (plan §10, Phase 3, T3.6).

- "Sync now": :func:`sync_source` runs one pull → ingest pass for a source.
- Beat schedule: :func:`sync_enabled_sources` is registered as a Celery task
  (see ``eil/workers/tasks.py``) so polling lands within the NFR.
- Health + lag: :func:`source_health`.
- Webhook receivers: :func:`sync_from_webhook` (used by the public
  ``POST /integrations/webhooks/...`` receiver).
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from connectors.sdk.protocol import RawRecord
from connectors.sdk.registry import get_connector
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.config import get_settings
from eil.core.models import utcnow
from eil.modules.integration.ingestion import upsert_record
from eil.modules.integration.models import (
    ApprovedSource,
    SyncConflict,
    SyncRun,
)
from eil.modules.integration.schemas import ApprovedSourceStatusRead

logger = structlog.get_logger(__name__)


async def sync_source(
    session: AsyncSession, source: ApprovedSource, *, triggered_by: str = "api"
) -> SyncRun:
    """Pull a source and ingest every record; returns the sync run."""
    run = SyncRun(
        source_id=source.id,
        status="running",
        started_at=utcnow(),
        triggered_by=triggered_by,
    )
    session.add(run)
    await session.commit()

    connector = get_connector(source.type)
    errors: list[str] = []
    count = 0
    cursor = source.sync_cursor
    try:
        for raw in connector.pull(cursor):
            count += 1
            cursor = raw.external_id
            try:
                await upsert_record(session, source, connector, raw)
            except Exception as exc:
                errors.append(f"{raw.external_id}: {exc}")
    except Exception as exc:
        errors.append(f"pull: {exc}")

    now = datetime.now(UTC)
    source.sync_cursor = cursor
    source.last_sync_at = now
    source.sync_lag_seconds = 0
    source.last_sync_error = "\n".join(errors) or None
    session.add(source)
    run.status = "failed" if errors else "succeeded"
    run.records_count = count
    run.errors = errors
    run.finished_at = now
    run.last_error = errors[0] if errors else None
    session.add(run)
    await session.commit()

    # AI Work Intelligence (plan §10, Phase 4): extraction pipeline trigger.
    if source.ai_processing_allowed and get_settings().ai_enabled:
        try:
            from eil.ai.pipeline.runner import run_ai_analysis

            await run_ai_analysis(session, source)
        except Exception as exc:
            logger.warning("ai_analysis_failed", source_id=str(source.id), error=str(exc))

    return run


async def sync_enabled_sources(
    session: AsyncSession, *, triggered_by: str = "beat"
) -> list[SyncRun]:
    """Celery Beat entry: sync every enabled source."""
    sources = (
        (await session.execute(select(ApprovedSource).where(ApprovedSource.enabled.is_(True))))
        .scalars()
        .all()
    )
    return [await sync_source(session, source, triggered_by=triggered_by) for source in sources]


async def sync_from_webhook(
    session: AsyncSession, source: ApprovedSource, records: list[RawRecord]
) -> int:
    """Ingest records pushed by a simulator webhook."""
    connector = get_connector(source.type)
    for raw in records:
        await upsert_record(session, source, connector, raw)
    source.last_sync_at = datetime.now(UTC)
    session.add(source)
    await session.commit()
    return len(records)


async def source_health(session: AsyncSession, source: ApprovedSource) -> ApprovedSourceStatusRead:
    """Connector health + sync lag + unresolved-conflict count (T3.6)."""
    connector = get_connector(source.type)
    health = connector.health()

    lag = None
    if source.last_sync_at is not None:
        last_sync = source.last_sync_at
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=UTC)
        lag = int((datetime.now(UTC) - last_sync).total_seconds())

    latest = (
        await session.execute(
            select(SyncRun)
            .where(SyncRun.source_id == source.id)
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    error_count = len(latest.errors) if latest is not None and latest.errors else 0

    unresolved = (
        await session.execute(
            select(func.count())
            .select_from(SyncConflict)
            .where(SyncConflict.source_id == source.id, SyncConflict.resolved.is_(False))
        )
    ).scalar_one()

    return ApprovedSourceStatusRead(
        source_id=source.id,
        health=health.status,
        last_sync_at=source.last_sync_at,
        lag_seconds=lag,
        error_count=error_count,
        conflicts_unresolved=unresolved,
    )
