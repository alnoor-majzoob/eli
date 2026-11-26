"""Recommendation optimiser (plan §9.3, Phase 6, T6.5)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from eil.modules.capacity import engine, optimiser
from eil.modules.capacity.models import (
    Certification,
    Competency,
    ResourceContract,
    ResourceSkill,
)
from eil.modules.execution.models import Allocation, WorkItem, WorkType
from eil.modules.identity.models import User

DELTA_KEYS = {
    "unmet_hours",
    "overload_hours",
    "reassignment_hours",
    "skill_gap_hours",
    "delayed_commitments",
}


def _week() -> date:
    return engine.week_start(date(2026, 11, 22))


def _mk_user(subject: str) -> User:
    return User(
        subject=subject, email=f"{subject}@eil.test", name=subject.replace("-", " ").title()
    )


async def _mk_contract(session, user_id, hours_per_week: str, week: date) -> None:
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


def _mk_task(
    session,
    title: str,
    week: date,
    effort: str,
    owner_id=None,
    required_competencies=None,
) -> WorkItem:
    attributes = {"effort_hours": effort}
    if required_competencies is not None:
        attributes["required_competencies"] = required_competencies
    task = WorkItem(
        type=WorkType.TASK,
        title=title,
        status="active",
        owner_id=owner_id,
        planned_start=week,
        planned_end=week + timedelta(days=6),
        attributes=attributes,
    )
    session.add(task)
    return task


async def test_optimise_returns_options_within_capacity(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user = _mk_user("opt-1")
        session.add(user)
        await session.flush()
        await _mk_contract(session, user.id, "40", week)
        _mk_task(session, "Fit task", week, "25")
        await session.commit()

        options = await optimiser.optimise(session)

    assert options
    for option in options:
        assert option["allocations"]
        assert sum(row["hours"] for row in option["allocations"]) == 25
        assert set(option["deltas"]) == DELTA_KEYS


async def test_optimise_reassigns_when_owner_is_full(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user_a = _mk_user("opt-2a")
        user_b = _mk_user("opt-2b")
        session.add_all([user_a, user_b])
        await session.flush()
        await _mk_contract(session, user_a.id, "40", week)
        await _mk_contract(session, user_b.id, "40", week)
        task = _mk_task(session, "Blocked task", week, "25", owner_id=user_a.id)
        await session.flush()
        session.add(
            Allocation(
                resource_id=user_a.id,
                work_item_id=task.id,
                kind="project",
                start_date=week,
                end_date=week + timedelta(days=6),
                hours_per_week=Decimal("40"),
            )
        )
        await session.commit()

        options = await optimiser.optimise(session)

    assert options
    reassign_option = next(o for o in options if o["strategy"] == "reassign")
    assert any(row["resource_id"] == user_b.id for row in reassign_option["allocations"])
    assert reassign_option["deltas"]["reassignment_hours"] > 0


async def test_optimise_respects_eligibility(app) -> None:
    week = _week()
    async with app.state.session_factory() as session:
        user_c = _mk_user("opt-3c")
        user_d = _mk_user("opt-3d")
        session.add_all([user_c, user_d])
        await session.flush()
        competency = Competency(name="Maintenance Engineer")
        session.add(competency)
        await session.flush()
        await _mk_contract(session, user_c.id, "40", week)
        await _mk_contract(session, user_d.id, "40", week)
        session.add(
            ResourceSkill(resource_id=user_c.id, competency_id=competency.id, proficiency=5)
        )
        session.add(
            Certification(
                resource_id=user_c.id,
                competency_id=competency.id,
                certificate_number="C-1",
                issued_date=week,
                status="active",
            )
        )
        _mk_task(
            session,
            "Certified task",
            week,
            "25",
            required_competencies=[str(competency.id)],
        )
        await session.commit()

        options = await optimiser.optimise(session)

    assert options
    assigned = {row["resource_id"] for option in options for row in option["allocations"]}
    assert user_c.id in assigned
    assert user_d.id not in assigned
