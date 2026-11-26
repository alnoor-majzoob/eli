"""Risk & escalation API (plan §10, Phase 7, T7.8)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from eil.core.models import utcnow
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.risk.models import Escalation
from eil.modules.risk.service import generate_escalations


async def test_risk_radar_rows(client, auth, app) -> None:
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        project = WorkItem(
            type=WorkType.PROJECT,
            title="Radar project",
            status="active",
            delivery_confidence=None,
        )
        session.add(project)
        await session.commit()

    radar = await client.get("/api/v1/risk/radar", headers=pm)
    assert radar.status_code == 200, radar.text
    row = next((r for r in radar.json() if r["item_id"] == str(project.id)), None)
    assert row is not None
    assert row["title"] == "Radar project"
    assert row["confidence"] is None or 0 <= row["confidence"] <= 1
    assert row["risk_score"] >= 0


async def test_escalations_list_and_acknowledge(client, auth, app) -> None:
    pm = await auth("portfolio_manager")
    async with app.state.session_factory() as session:
        project = WorkItem(type=WorkType.PROJECT, title="Escalation target", status="active")
        session.add(project)
        await session.flush()
        escalation = Escalation(
            work_item_id=project.id,
            root_cause="Target delivery confidence is low.",
            recommended_actions=[],
            target_role="dept_head",
            due_at=utcnow() + timedelta(days=2),
            sla_days=2,
        )
        session.add(escalation)
        await session.commit()
        escalation_id = str(escalation.id)

    listed = await client.get("/api/v1/escalations", headers=pm)
    assert listed.status_code == 200
    assert any(row["id"] == escalation_id for row in listed.json())

    acknowledged = await client.patch(
        f"/api/v1/escalations/{escalation_id}/acknowledge", headers=pm
    )
    assert acknowledged.status_code == 200, acknowledged.text
    assert acknowledged.json()["status"] == "acknowledged"


async def test_generate_escalations_creates_rows(app) -> None:
    async with app.state.session_factory() as session:
        commitment = WorkItem(
            type=WorkType.COMMITMENT,
            title="Escalation trigger",
            status="active",
            delivery_confidence=Decimal("0.20"),
        )
        session.add(commitment)
        await session.commit()
        created = await generate_escalations(session)
        assert any(row.target_role == "dept_head" for row in created)
