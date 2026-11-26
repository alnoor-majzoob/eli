"""Celery application scaffold.

Local mode (no Redis) uses the inline outbox dispatcher in the API process. In the
compose stack, Celery Beat drains the outbox here; later phases add ingest / ai /
sync / simulate / recalc queues.
"""

from __future__ import annotations

import asyncio

import structlog
from celery import Celery

from eil.core.config import get_settings
from eil.core.db import create_engine, create_session_factory
from eil.core.outbox import dispatch_pending

logger = structlog.get_logger(__name__)


def _build_app() -> Celery:
    settings = get_settings()
    broker = settings.redis_url or "memory://"
    backend = settings.redis_url or "cache+memory://"
    app = Celery("eil", broker=broker, backend=backend, include=["eil.workers.tasks"])
    app.conf.update(
        task_always_eager=settings.celery_eager,
        task_eager_propagates=True,
        task_track_started=True,
        timezone="UTC",
        enable_utc=True,
        beat_schedule={
            "outbox-dispatch": {
                "task": "eil.workers.dispatch_outbox",
                "schedule": 5.0,
            },
            "audit-chain-verify": {
                "task": "eil.workers.verify_audit_chain",
                "schedule": 86400.0,
            },
            "approval-escalation": {
                "task": "eil.workers.escalate_overdue",
                "schedule": 3600.0,
            },
            "integration-sync": {
                "task": "eil.workers.sync_sources",
                "schedule": 60.0,
            },
        },
    )
    return app


celery_app = _build_app()


async def _dispatch_once() -> int:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            return await dispatch_pending(session)
    finally:
        await engine.dispose()


@celery_app.task(name="eil.workers.dispatch_outbox")
def dispatch_outbox() -> int:
    """Drain a batch of pending domain events."""
    return asyncio.run(_dispatch_once())
