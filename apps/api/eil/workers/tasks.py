"""Celery tasks for governance and audit maintenance."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from eil.core.config import get_settings
from eil.core.db import create_engine, create_session_factory
from eil.modules.audit.service import verify_chain
from eil.modules.governance.service import escalate_overdue_approvals
from eil.modules.integration.sync import sync_enabled_sources
from eil.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


async def _verify_chain_once() -> dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            result = await verify_chain(session)
            if not result.ok:
                logger.error("audit_chain_broken", broken_at=result.broken_at, rows=result.rows)
            return {"rows": result.rows, "broken_at": result.broken_at, "ok": result.ok}
    finally:
        await engine.dispose()


async def _escalate_once() -> int:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return await escalate_overdue_approvals(session, now=datetime.now(UTC))
    finally:
        await engine.dispose()


@celery_app.task(name="eil.workers.verify_audit_chain")
def verify_audit_chain() -> dict[str, Any]:
    """Nightly hash-chain verification; logs and returns a machine-readable result."""
    return asyncio.run(_verify_chain_once())


@celery_app.task(name="eil.workers.escalate_overdue")
def escalate_overdue() -> int:
    """Escalate pending approvals whose SLA has elapsed."""
    return asyncio.run(_escalate_once())


async def _sync_sources_once() -> list[str]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            runs = await sync_enabled_sources(session, triggered_by="beat")
            return [f"{run.source_id}: {run.status} ({run.records_count} records)" for run in runs]
    finally:
        await engine.dispose()


@celery_app.task(name="eil.workers.sync_sources")
def sync_sources() -> list[str]:
    """Beat entry: sync every enabled approved source (NFR: ≤ 60 s)."""
    return asyncio.run(_sync_sources_once())
