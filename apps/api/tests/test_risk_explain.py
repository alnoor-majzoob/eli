"""Explanation service (plan §9.5, Phase 7, T7.7)."""

from __future__ import annotations

from datetime import date, timedelta

from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.risk.explain import explain_confidence


async def test_explain_confidence_fact_sheet_and_template_fallback(app) -> None:
    week = date(2026, 12, 1)
    async with app.state.session_factory() as session:
        item = WorkItem(
            type=WorkType.MILESTONE,
            title="Turnaround milestone",
            status="active",
            planned_start=week,
            planned_end=week + timedelta(days=20),
        )
        session.add(item)
        await session.commit()

        explanation = await explain_confidence(session, None, item.id)

        assert explanation["item_id"] == item.id
        sheet = explanation["fact_sheet"]
        assert sheet["title"] == "Turnaround milestone"
        assert sheet["committed_days"] == 21
        assert sheet["p50_finish"] is not None
        assert 0 <= explanation["confidence"] <= 1
        assert explanation["narrative"] is None or isinstance(explanation["narrative"], str)
