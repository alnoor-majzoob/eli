"""confidence_changed domain events (plan Phase 7, T7.5).

``recalc_confidence`` and ``rollup_confidence`` emit one ``confidence_changed``
event per updated item through the outbox (event-driven recalculation pipeline).
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select

from eil.core.outbox import OutboxEvent
from eil.modules.execution.models import WorkItem, WorkItemStatus, WorkType
from eil.modules.risk.service import recalc_confidence


async def _confidence_changed_rows(session, item_id: UUID) -> list[OutboxEvent]:
    result = await session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "confidence_changed")
    )
    return [row for row in result.scalars().all() if row.payload.get("item_id") == str(item_id)]


async def test_recalc_confidence_emits_confidence_changed_events(app) -> None:
    async with app.state.session_factory() as session:
        item = WorkItem(
            type=WorkType.COMMITMENT,
            title="Commitment with schedule",
            status=WorkItemStatus.ACTIVE,
            planned_start=date.today(),
            planned_end=date.today() + timedelta(days=7),
            baseline_end=date.today() + timedelta(days=7),
        )
        session.add(item)
        await session.commit()
        item_id = item.id

    async with app.state.session_factory() as session:
        updated = await recalc_confidence(session, [item_id])
        rows = await _confidence_changed_rows(session, item_id)

    assert item_id in updated
    assert len(rows) == 1
    assert rows[0].payload["confidence"] == float(updated[item_id])
