"""Transactional outbox: events are persisted with the business change.

In ``compose`` mode a Celery beat task drains the table. In local mode (no Redis)
an in-process dispatcher loop drains it from the API lifespan.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import JSON, DateTime, Integer, String, Text, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.events import handle_event

logger = structlog.get_logger(__name__)

MAX_ATTEMPTS = 5
DISPATCH_BATCH_SIZE = 50


class OutboxEvent(Base):
    """Append-only domain event awaiting dispatch."""

    __tablename__ = "outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<OutboxEvent {self.event_type} id={self.id} processed={self.processed_at}>"


async def emit(session: AsyncSession, event_type: str, payload: dict[str, Any]) -> OutboxEvent:
    """Persist a domain event in the current transaction."""
    event = OutboxEvent(event_type=event_type, payload=payload)
    session.add(event)
    await session.flush()
    logger.debug("outbox_emit", event_type=event_type, event_id=str(event.id))
    return event


async def dispatch_pending(session: AsyncSession, limit: int = DISPATCH_BATCH_SIZE) -> int:
    """Dispatch pending events; returns the number of events processed."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.processed_at.is_(None))
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)

    events = list((await session.execute(stmt)).scalars())
    if not events:
        return 0

    processed = 0
    for event in events:
        try:
            await handle_event(event)
        except Exception as exc:
            event.attempts += 1
            event.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "outbox_handler_failed",
                event_type=event.event_type,
                event_id=str(event.id),
                attempts=event.attempts,
            )
            if event.attempts >= MAX_ATTEMPTS:
                event.processed_at = datetime.now(UTC)
                logger.error(
                    "outbox_dead_lettered",
                    event_type=event.event_type,
                    event_id=str(event.id),
                )
        else:
            event.processed_at = datetime.now(UTC)
            processed += 1
    await session.commit()
    return processed


async def run_dispatcher_loop(
    session_factory: async_sessionmaker[AsyncSession], poll_seconds: float = 1.0
) -> None:
    """Drain the outbox forever (local mode). Cancelled at shutdown."""
    logger.info("outbox_dispatcher_started", poll_seconds=poll_seconds)
    try:
        while True:
            try:
                async with session_factory() as session:
                    await dispatch_pending(session)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("outbox_dispatch_iteration_failed")
            await asyncio.sleep(poll_seconds)
    except asyncio.CancelledError:
        logger.info("outbox_dispatcher_stopped")
        raise
