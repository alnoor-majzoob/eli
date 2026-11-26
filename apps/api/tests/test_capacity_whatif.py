"""What-if scenarios and impact analysis (plan §9.4, Phase 6, T6.4/T6.6)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from eil.core.errors import AppError
from eil.core.security import Principal
from eil.modules.audit.models import AuditLog
from eil.modules.capacity import engine, whatif
from eil.modules.capacity.analysis import impact_analysis
from eil.modules.capacity.models import ResourceContract
from eil.modules.execution.models import Allocation, WorkItem, WorkLink, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext


def _week() -> date:
    return engine.week_start(date(2026, 11, 22))


def _ctx() -> PermissionContext:
    principal = Principal(subject="cap-whatif", name="Cap Whatif", email="cap-whatif@eil.test")
    user = User(subject="cap-whatif", email="cap-whatif@eil.test", name="Cap Whatif")
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("project_manager",),
        scope="global",
        permission="work.view",
    )


def _mk_user(subject: str) -> User:
    return User(
        subject=subject, email=f"{subject}@eil.test", name=subject.replace("-", " ").title()
    )


async def _mk_contract(session, user_id: UUID, hours_per_week: str, week: date) -> None:
    session.add(
        ResourceContract(
            resource_id=user_id,
            start_date=week,
            end_date=week + timedelta(days=6),
            hours_per_week=Decimal(hours_per_week),
            status="active",
        )
    )
    await session.flush()


async def _mk_allocation(
    session, user_id: UUID, week: date, hours_per_week: str, work_item_id: UUID | None = None
) -> Allocation:
    allocation = Allocation(
        resource_id=user_id,
        work_item_id=work_item_id,
        start_date=week,
        end_date=week + timedelta(days=6),
        kind="project",
        hours_per_week=Decimal(hours_per_week),
    )
    session.add(allocation)
    await session.flush()
    return allocation


async def test_scenario_demand_reads_through_overlay(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-w1")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        allocation = await _mk_allocation(session, user.id, week, "20")
        scenario = await whatif.create_scenario(session, name="Adjust", author_id=user.id)
        await whatif.add_scenario_change(
            session,
            scenario.id,
            allocation_id=allocation.id,
            payload={"hours_per_week": Decimal("30")},
        )
        await session.commit()

        baseline = await engine.demand_hours(session, user.id, week + timedelta(days=3))
        scenario_demand = await engine.demand_hours(
            session, user.id, week + timedelta(days=3), scenario.id
        )
        assert baseline == Decimal("20")
        assert scenario_demand == Decimal("30")


async def test_scenario_new_allocation_reads_through(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-w2")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        scenario = await whatif.create_scenario(session, name="Add work", author_id=user.id)
        await whatif.add_scenario_change(
            session,
            scenario.id,
            payload={
                "resource_id": user.id,
                "start_date": week,
                "end_date": week + timedelta(days=6),
                "hours_per_week": Decimal("10"),
            },
        )
        await session.commit()

        assert await engine.demand_hours(session, user.id, week + timedelta(days=3)) == Decimal("0")
        assert await engine.demand_hours(
            session, user.id, week + timedelta(days=3), scenario.id
        ) == Decimal("10")


async def test_promote_scenario_applies_overlay(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-w3")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        allocation = await _mk_allocation(session, user.id, week, "20")
        project = WorkItem(type=WorkType.PROJECT, title="Boost project", status="active")
        session.add(project)
        await session.flush()
        scenario = await whatif.create_scenario(session, name="Boost", author_id=user.id)
        await whatif.add_scenario_change(
            session,
            scenario.id,
            allocation_id=allocation.id,
            payload={"hours_per_week": Decimal("30")},
        )
        await whatif.add_scenario_change(
            session,
            scenario.id,
            work_item_id=project.id,
            payload={"priority_score": Decimal("90")},
        )
        await session.commit()

        await whatif.promote_scenario(session, _ctx(), scenario.id)
        await session.refresh(allocation)
        await session.refresh(project)
        await session.refresh(scenario)

        assert allocation.hours_per_week == Decimal("30")
        assert project.priority_score == Decimal("90")
        assert scenario.promoted is True
        audit = (
            (await session.execute(select(AuditLog).where(AuditLog.action == "scenario.promoted")))
            .scalars()
            .all()
        )
        assert any(str(row.entity_id) == str(scenario.id) for row in audit)
        with pytest.raises(AppError) as excinfo:
            await whatif.promote_scenario(session, _ctx(), scenario.id)
        assert excinfo.value.status_code == 409


async def test_scenario_metrics(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-w4")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        await _mk_allocation(session, user.id, week, "50")
        scenario = await whatif.create_scenario(session, name="Overloaded", author_id=user.id)
        allocation = (
            (
                await session.execute(
                    select(Allocation).where(
                        Allocation.resource_id == user.id,
                        Allocation.start_date == week,
                    )
                )
            )
            .scalars()
            .one()
        )
        await whatif.add_scenario_change(
            session,
            scenario.id,
            allocation_id=allocation.id,
            payload={"hours_per_week": Decimal("50")},
            reason="Hold the line",
        )
        await session.commit()

        metrics = await whatif.scenario_metrics(session, scenario.id)
        assert metrics["overload_hours"] == Decimal("10")
        assert metrics["red_weeks"] == 1
        assert metrics["delayed_commitments"] == 0
        assert metrics["cost_proxy"] == Decimal("50")


async def test_impact_analysis_lists_affected_commitments(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-w5")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        project = WorkItem(type=WorkType.PROJECT, title="Big project", status="active")
        commitment = WorkItem(
            type=WorkType.COMMITMENT, title="Reliability commitment", status="active"
        )
        session.add_all([project, commitment])
        await session.flush()
        session.add(
            WorkLink(
                src_id=project.id,
                dst_id=commitment.id,
                link_type="fulfils",
                origin="system",
                status="active",
                weight=1,
            )
        )
        await _mk_allocation(session, user.id, week, "45", work_item_id=project.id)
        await session.commit()

        overloads = await engine.detect_overloads(session, week + timedelta(days=3))
        assert any(row["resource_id"] == user.id for row in overloads)

        results = await impact_analysis(session, _ctx(), overloads)
        assert len(results) == 1
        affected_ids = [row["id"] for row in results[0]["affected"]]
        assert commitment.id in affected_ids
        assert all(
            row["type"] in ("commitment", "project", "objective") for row in results[0]["affected"]
        )


async def test_expire_scenarios(app) -> None:
    async with app.state.session_factory() as session:
        user = _mk_user("cap-w6")
        session.add(user)
        await session.flush()
        expired_at = date.today() - timedelta(days=1)
        scenario = await whatif.create_scenario(
            session, name="Old", author_id=user.id, expires_at=expired_at
        )
        future = await whatif.create_scenario(
            session, name="New", author_id=user.id, expires_at=date.today() + timedelta(days=10)
        )
        await session.commit()

        rows = await whatif.expire_scenarios(session)
        await session.refresh(scenario)
        await session.refresh(future)
        assert [row.id for row in rows] == [scenario.id]
        assert scenario.expired is True
        assert future.expired is False
