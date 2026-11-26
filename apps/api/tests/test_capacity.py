"""Capacity engine (plan §9.2, Phase 6, T6.1-T6.3)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from eil.modules.capacity import engine
from eil.modules.capacity.models import (
    BauBaseline,
    Certification,
    Competency,
    ResourceCalendar,
    ResourceContract,
    ResourceLeave,
    ResourceSkill,
)
from eil.modules.execution.models import Allocation
from eil.modules.identity.models import User


def _mk_user(subject: str) -> User:
    return User(
        subject=subject, email=f"{subject}@eil.test", name=subject.replace("-", " ").title()
    )


def _week() -> date:
    return engine.week_start(date(2026, 11, 22))


async def _mk_contract(session, user_id, hours_per_week: str, week: date, status: str = "active"):
    session.add(
        ResourceContract(
            resource_id=user_id,
            start_date=week,
            end_date=week + timedelta(days=6),
            hours_per_week=Decimal(hours_per_week),
            status=status,
        )
    )
    await session.flush()


async def _mk_allocation(
    session,
    user_id,
    week: date,
    hours_per_week: str,
    scenario_id=None,
):
    session.add(
        Allocation(
            resource_id=user_id,
            start_date=week,
            end_date=week + timedelta(days=6),
            kind="project",
            hours_per_week=Decimal(hours_per_week),
            scenario_id=scenario_id,
        )
    )
    await session.flush()


async def test_contracted_from_active_contract(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-contract")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        await session.commit()
        assert await engine.contracted_hours(session, user.id, week + timedelta(days=3)) == Decimal(
            "40"
        )


async def test_contracted_from_calendar_fallback(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-calendar")
        session.add(user)
        await session.flush()
        session.add(
            ResourceCalendar(
                resource_id=user.id,
                monday=True,
                tuesday=True,
                wednesday=False,
                thursday=True,
                friday=True,
                daily_hours=Decimal("8"),
            )
        )
        await session.commit()
        assert await engine.contracted_hours(session, user.id, week + timedelta(days=2)) == Decimal(
            "32"
        )


async def test_contracted_zero_without_contract_or_calendar(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-none")
        session.add(user)
        await session.commit()
        assert await engine.contracted_hours(session, user.id, week) == Decimal("0")


async def test_leave_hours_pro_rated(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-leave")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        session.add(
            ResourceLeave(
                resource_id=user.id,
                start_date=week + timedelta(days=2),
                end_date=week + timedelta(days=5),
                hours=Decimal("16"),
                leave_type="annual",
            )
        )
        await session.commit()
        assert await engine.leave_hours(session, user.id, week + timedelta(days=3)) == Decimal("16")


async def test_bau_hours_from_baseline(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-bau")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        session.add(BauBaseline(resource_id=user.id, bau_percent=Decimal("50")))
        await session.commit()
        assert await engine.bau_hours(session, user.id, week + timedelta(days=3)) == Decimal("20")


async def test_available_demand_and_utilisation(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-util")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        await _mk_allocation(session, user.id, week, "30")
        await session.commit()
        assert await engine.available_hours(session, user.id, week + timedelta(days=3)) == Decimal(
            "40"
        )
        assert await engine.demand_hours(session, user.id, week + timedelta(days=3)) == Decimal(
            "30"
        )
        assert await engine.utilisation(session, user.id, week + timedelta(days=3)) == Decimal(
            "0.75"
        )
        assert (
            engine.capacity_status(
                await engine.utilisation(session, user.id, week + timedelta(days=3))
            )
            == "green"
        )


async def test_detect_overloads(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        over_user = _mk_user("cap-over")
        under_user = _mk_user("cap-under")
        session.add_all([over_user, under_user])
        await session.flush()
        await _mk_contract(session, over_user.id, "40", week)
        await _mk_contract(session, under_user.id, "40", week)
        await _mk_allocation(session, over_user.id, week, "45")
        await _mk_allocation(session, under_user.id, week, "30")
        await session.commit()

        overloads = await engine.detect_overloads(session, week + timedelta(days=3))
        over_rows = [row for row in overloads if row["resource_id"] == over_user.id]
        under_rows = [row for row in overloads if row["resource_id"] == under_user.id]
        assert len(over_rows) == 1
        assert over_rows[0]["status"] == "red"
        assert over_rows[0]["utilisation"] > Decimal("1.00")
        assert under_rows == []


async def test_scenario_allocations_are_not_baseline_demand(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-scenario")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        await _mk_allocation(session, user.id, week, "20", scenario_id=uuid4())
        await session.commit()
        assert await engine.demand_hours(session, user.id, week + timedelta(days=3)) == Decimal("0")


async def test_eligible_resources_requires_valid_certification(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-cert")
        session.add(user)
        competency = Competency(name="Rotating Equipment Engineer")
        session.add_all([user, competency])
        await session.flush()
        session.add(ResourceSkill(resource_id=user.id, competency_id=competency.id, proficiency=5))
        session.add(
            Certification(
                resource_id=user.id,
                competency_id=competency.id,
                certificate_number="CERT-1",
                issued_date=week - timedelta(days=1),
                expiry_date=week + timedelta(days=30),
                status="active",
            )
        )
        await session.commit()
        assert await engine.eligible_resources(
            session, week + timedelta(days=3), competency.id
        ) == [user.id]


async def test_competency_shortage_on_certified_population(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("cap-shortage")
        session.add(user)
        competency = Competency(name="Vibration Analyst")
        session.add_all([user, competency])
        await session.flush()
        session.add(ResourceSkill(resource_id=user.id, competency_id=competency.id, proficiency=4))
        session.add(
            Certification(
                resource_id=user.id,
                competency_id=competency.id,
                status="active",
                expiry_date=week + timedelta(days=30),
            )
        )
        await _mk_contract(session, user.id, "40", week)
        await _mk_allocation(session, user.id, week, "45")
        await session.commit()
        shortages = await engine.competency_shortage(session, week + timedelta(days=3))
        assert [s["competency_id"] for s in shortages] == [competency.id]
        assert shortages[0]["certified_resources"] == 1
        assert shortages[0]["utilisation"] > Decimal("1.00")


async def test_certification_validity_windows(app) -> None:
    week = _week()
    valid = Certification(status="active", expiry_date=week + timedelta(days=30))
    expired = Certification(status="active", expiry_date=week - timedelta(days=1))
    revoked = Certification(status="revoked", expiry_date=None)
    unissued = Certification(
        status="active", issued_date=week + timedelta(days=1), expiry_date=None
    )
    assert engine.is_certification_valid(valid, week + timedelta(days=3))
    assert not engine.is_certification_valid(expired, week + timedelta(days=3))
    assert not engine.is_certification_valid(revoked, week + timedelta(days=3))
    assert not engine.is_certification_valid(unissued, week + timedelta(days=3))
