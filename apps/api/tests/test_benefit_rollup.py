"""Benefit → objective roll-up widgets (plan Phase 5, T5.7)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from httpx import AsyncClient

from eil.core.security import Principal
from eil.modules.execution.models import BenefitMeasurement, WorkItem, WorkLink
from eil.modules.execution.service import benefit_rollup
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext


def _ctx() -> PermissionContext:
    principal = Principal(subject="rollup-test", name="Rollup", email="rollup@eil.test")
    user = User(subject="rollup-test", email="rollup@eil.test", name="Rollup")
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("portfolio_manager",),
        scope="global",
        permission="work.view",
    )


async def test_benefit_rollup_objective_rows(app) -> None:
    async with app.state.session_factory() as session:
        objective = WorkItem(type="objective", title="K-201 availability ≥ 99%", status="active")
        session.add(objective)
        await session.flush()
        benefit = WorkItem(type="benefit", title="Zero unplanned downtime", status="active")
        session.add(benefit)
        await session.flush()
        kr = WorkItem(type="key_result", title="99.9% monthly availability", status="active")
        session.add(kr)
        await session.flush()
        session.add(
            WorkLink(src_id=objective.id, dst_id=benefit.id, link_type="realizes", status="active")
        )
        session.add(
            WorkLink(src_id=objective.id, dst_id=kr.id, link_type="aligns_to", status="active")
        )
        session.add(
            BenefitMeasurement(
                benefit_id=benefit.id,
                period=date(2026, 11, 1),
                actual=Decimal("4"),
                target=Decimal("10"),
                forecast=Decimal("10"),
            )
        )
        await session.commit()

    async with app.state.session_factory() as session:
        rows = await benefit_rollup(session, _ctx())

    assert len(rows) == 1
    row = rows[0]
    assert row.objective_id == objective.id
    assert row.title == "K-201 availability ≥ 99%"
    assert row.kr_count == 1
    assert row.benefit_count == 1
    assert row.total_actual == Decimal("4")
    assert row.total_target == Decimal("10")
    assert row.total_forecast == Decimal("10")
    assert row.latest_actual_at == date(2026, 11, 1)
    assert row.on_track is False


async def test_benefit_rollup_empty(app) -> None:
    async with app.state.session_factory() as session:
        rows = await benefit_rollup(session, _ctx())
    assert rows == []


async def test_benefit_rollup_endpoint(client: AsyncClient, auth) -> None:
    headers = await auth("executive")
    response = await client.get("/api/v1/items/benefit-rollup", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
