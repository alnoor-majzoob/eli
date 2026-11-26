"""Capacity engine per plan §9.2 (Phase 6, T6.1-T6.3).

Deterministic formulas (R3: the engine computes; applications narrate):

.. code-block:: text

    available(r, w) = contracted_hours(r, w) - leave(r, w) - bau_hours(r, w)
    demand(r, w)    = sum(allocation_hours(a, r, w)) for baseline (scenario_id NULL)
    utilisation     = demand / available

Overload thresholds are configuration (`capacity_amber_pct`, `capacity_red_pct`,
`capacity_sustained_red_weeks` on :class:`eil.core.config.Settings`).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.config import get_settings
from eil.modules.capacity.models import (
    BauBaseline,
    Certification,
    Competency,
    ResourceCalendar,
    ResourceContract,
    ResourceLeave,
    ResourceSkill,
    ScenarioChange,
)
from eil.modules.execution.models import Allocation, WorkItem, WorkItemStatus, WorkType

ZERO = Decimal("0")
HUNDRED = Decimal("100")
_WEEK_DAY_NAMES = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def week_start(on: date) -> date:
    """Monday of the week containing ``on``."""
    return on - timedelta(days=on.weekday())


def _dec(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    return Decimal(str(value))


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _as_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _overlap_days(start: date | None, end: date | None, week: date) -> int:
    """Days of ``[start, end]`` overlapping the week ``[week, week+6]``."""
    if start is None or end is None:
        return 0
    lo = max(start, week)
    hi = min(end, week + timedelta(days=6))
    if hi < lo:
        return 0
    return (hi - lo).days + 1


def days_between(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


async def contracted_hours(session: AsyncSession, resource_id: UUID, on: date) -> Decimal:
    """``contracted_hours(r, w)``: active contract hours, else calendar week hours."""
    week = week_start(on)
    contract = (
        (
            await session.execute(
                select(ResourceContract)
                .where(
                    ResourceContract.resource_id == resource_id,
                    ResourceContract.status == "active",
                    ResourceContract.start_date <= week,
                    ResourceContract.end_date >= week,
                )
                .order_by(ResourceContract.start_date.desc())
            )
        )
        .scalars()
        .first()
    )
    if contract is not None:
        return _dec(contract.hours_per_week)
    calendar = (
        (
            await session.execute(
                select(ResourceCalendar).where(ResourceCalendar.resource_id == resource_id)
            )
        )
        .scalars()
        .first()
    )
    if calendar is None:
        return ZERO
    total = ZERO
    for index in range(7):
        day = week + timedelta(days=index)
        if getattr(calendar, _WEEK_DAY_NAMES[day.weekday()]):
            total += _dec(calendar.daily_hours)
    return total


async def leave_hours(session: AsyncSession, resource_id: UUID, on: date) -> Decimal:
    """``leave(r, w)``: leave hours overlapping the week of ``on`` (pro-rated)."""
    week = week_start(on)
    leaves = (
        (
            await session.execute(
                select(ResourceLeave).where(
                    ResourceLeave.resource_id == resource_id,
                    ResourceLeave.start_date <= week + timedelta(days=6),
                    ResourceLeave.end_date >= week,
                )
            )
        )
        .scalars()
        .all()
    )
    total = ZERO
    for leave in leaves:
        overlap_start = max(leave.start_date, week)
        overlap_end = min(leave.end_date, week + timedelta(days=6))
        if overlap_end < overlap_start:
            continue
        days = (overlap_end - overlap_start).days + 1
        span = (leave.end_date - leave.start_date).days + 1
        total += _dec(leave.hours) * Decimal(days) / Decimal(span)
    return total


async def bau_hours(session: AsyncSession, resource_id: UUID, on: date) -> Decimal:
    """``bau_hours(r, w)``: BAU baseline % of contracted hours."""
    bau = (
        (await session.execute(select(BauBaseline).where(BauBaseline.resource_id == resource_id)))
        .scalars()
        .first()
    )
    if bau is None:
        return ZERO
    base = await contracted_hours(session, resource_id, on)
    return base * _dec(bau.bau_percent) / HUNDRED


async def _calendar(session: AsyncSession, resource_id: UUID) -> ResourceCalendar | None:
    return (
        (
            await session.execute(
                select(ResourceCalendar).where(ResourceCalendar.resource_id == resource_id)
            )
        )
        .scalars()
        .first()
    )


def _working_days(week: date, calendar: ResourceCalendar | None) -> list[date]:
    """Working days of the week — calendar flags, or Mon-Fri without a calendar row."""
    if calendar is not None:
        return [
            day
            for i in range(7)
            if getattr(calendar, _WEEK_DAY_NAMES[(week + timedelta(days=i)).weekday()])
            for day in [week + timedelta(days=i)]
        ]
    return [week + timedelta(days=i) for i in range(7) if (week + timedelta(days=i)).weekday() < 5]


async def available_hours(
    session: AsyncSession, resource_id: UUID, on: date, scenario_id: UUID | None = None
) -> Decimal:
    """``available(r, w) = contracted - leave - bau``."""
    base = await contracted_hours(session, resource_id, on)
    return (
        base
        - await leave_hours(session, resource_id, on)
        - await bau_hours(session, resource_id, on)
    )


async def scenario_changes_by_allocation(
    session: AsyncSession, scenario_id: UUID
) -> dict[UUID | None, ScenarioChange]:
    """Scenario changes keyed by edited allocation id (``None`` = new allocation)."""
    rows = (
        (
            await session.execute(
                select(ScenarioChange).where(ScenarioChange.scenario_id == scenario_id)
            )
        )
        .scalars()
        .all()
    )
    return {row.allocation_id: row for row in rows}


async def task_spreading_hours(session: AsyncSession, resource_id: UUID, on: date) -> Decimal:
    """Tasks without an explicit allocation spread ``effort_hours`` evenly over the
    working days in ``[planned_start, planned_end]`` (plan §9.2)."""
    week = week_start(on)
    working = _working_days(week, await _calendar(session, resource_id))
    if not working:
        return ZERO
    week_span = [day for day in working if week <= day <= week + timedelta(days=6)]
    if not week_span:
        return ZERO
    allocated_work_items = {
        row.work_item_id
        for row in (
            (
                await session.execute(
                    select(Allocation).where(
                        Allocation.resource_id == resource_id,
                        Allocation.scenario_id.is_(None),
                        Allocation.start_date <= week + timedelta(days=6),
                        Allocation.end_date >= week,
                        Allocation.work_item_id.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if row.work_item_id is not None
    }
    tasks = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.owner_id == resource_id,
                    WorkItem.type == WorkType.TASK,
                    WorkItem.planned_start.isnot(None),
                    WorkItem.planned_end.isnot(None),
                    WorkItem.status.notin_((WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)),
                )
            )
        )
        .scalars()
        .all()
    )
    total = ZERO
    for task in tasks:
        if task.id in allocated_work_items:
            continue
        effort = _dec((task.attributes or {}).get("effort_hours"))
        if effort <= ZERO:
            continue
        planned_start = task.planned_start
        planned_end = task.planned_end
        if planned_start is None or planned_end is None:
            continue
        window_days = [day for day in working if planned_start <= day <= planned_end]
        if not window_days:
            continue
        this_week = [day for day in window_days if week <= day <= week + timedelta(days=6)]
        if not this_week:
            continue
        total += effort * Decimal(len(this_week)) / Decimal(len(window_days))
    return total


async def demand_hours(
    session: AsyncSession, resource_id: UUID, on: date, scenario_id: UUID | None = None
) -> Decimal:
    """``demand(r, w)``: baseline (scenario-less) allocation hours overlapping the week,
    or the given scenario overlay (plan §9.2); tasks without explicit allocation spread
    effort (T6.2)."""
    week = week_start(on)
    if scenario_id is None:
        total = ZERO
        for row in (
            (
                await session.execute(
                    select(Allocation).where(
                        Allocation.resource_id == resource_id,
                        Allocation.scenario_id.is_(None),
                        Allocation.start_date <= week + timedelta(days=6),
                        Allocation.end_date >= week,
                        Allocation.hours_per_week.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            total += _dec(row.hours_per_week)
        return total + await task_spreading_hours(session, resource_id, on)

    changes = await scenario_changes_by_allocation(session, scenario_id)
    edited_ids = {cid for cid in changes if cid is not None}
    total = ZERO
    for row in (
        (
            await session.execute(
                select(Allocation).where(
                    Allocation.resource_id == resource_id,
                    Allocation.start_date <= week + timedelta(days=6),
                    Allocation.end_date >= week,
                    Allocation.hours_per_week.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    ):
        if row.id in edited_ids:
            change = changes[row.id]
            payload = change.payload or {}
            if (
                _overlap_days(
                    _as_date(payload.get("start_date", row.start_date)),
                    _as_date(payload.get("end_date", row.end_date)),
                    week,
                )
                == 0
            ):
                continue
            total += _dec(payload.get("hours_per_week", row.hours_per_week))
        elif row.scenario_id is None or row.scenario_id == scenario_id:
            total += _dec(row.hours_per_week)
    for change in changes.values():
        if change.allocation_id is None:
            payload = change.payload or {}
            if str(_as_uuid(payload.get("resource_id"))) == str(resource_id) and _overlap_days(
                _as_date(payload.get("start_date")), _as_date(payload.get("end_date")), week
            ):
                total += _dec(payload.get("hours_per_week"))
    return total


async def utilisation(
    session: AsyncSession, resource_id: UUID, on: date, scenario_id: UUID | None = None
) -> Decimal | None:
    """``utilisation = demand / available``; ``None`` when available is zero."""
    available = await available_hours(session, resource_id, on, scenario_id)
    if available <= ZERO:
        return None
    return (await demand_hours(session, resource_id, on, scenario_id)) / available


def capacity_status(util: Decimal | None) -> str | None:
    """RAG per thresholds: red > red_pct, amber > amber_pct, else green (config)."""
    if util is None:
        return None
    settings = get_settings()
    if util > Decimal(settings.capacity_red_pct) / HUNDRED:
        return "red"
    if util > Decimal(settings.capacity_amber_pct) / HUNDRED:
        return "amber"
    return "green"


def is_certification_valid(cert: Certification, on: date) -> bool:
    """Active certification valid for every day of the week containing ``on``."""
    week = week_start(on)
    return (
        cert.status == "active"
        and (cert.issued_date is None or cert.issued_date <= week)
        and (cert.expiry_date is None or cert.expiry_date >= week + timedelta(days=6))
    )


async def eligible_resources(
    session: AsyncSession,
    week_start_on: date,
    competency_id: UUID,
    min_proficiency: int | None = None,
) -> list[UUID]:
    """Resources holding a valid skill (at ``min_proficiency`` when set) and a
    certification valid for the whole window."""
    skills = (
        (
            await session.execute(
                select(ResourceSkill).where(ResourceSkill.competency_id == competency_id)
            )
        )
        .scalars()
        .all()
    )
    eligible: list[UUID] = []
    for skill in skills:
        if min_proficiency is not None and skill.proficiency < min_proficiency:
            continue
        certs = (
            (
                await session.execute(
                    select(Certification).where(
                        Certification.resource_id == skill.resource_id,
                        Certification.competency_id == competency_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if any(is_certification_valid(cert, week_start_on) for cert in certs):
            eligible.append(skill.resource_id)
    return sorted(set(eligible), key=str)


async def detect_overloads(
    session: AsyncSession, on: date, scenario_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Per-resource overloads for the week of ``on`` (plan §9.2); reads the scenario
    overlay when ``scenario_id`` is given."""
    week = week_start(on)
    resource_ids: set[UUID] = set()
    allocation_filters: list[Any] = [
        Allocation.start_date <= week + timedelta(days=6),
        Allocation.end_date >= week,
    ]
    if scenario_id is None:
        allocation_filters.append(Allocation.scenario_id.is_(None))
    else:
        allocation_filters.append(
            (Allocation.scenario_id == scenario_id)
            | (Allocation.scenario_id.is_(None) & Allocation.hours_per_week.isnot(None))
        )
    for resource_id in (
        (
            await session.execute(
                select(Allocation.resource_id).where(*allocation_filters).distinct()
            )
        )
        .scalars()
        .all()
    ):
        resource_ids.add(resource_id)
    resource_ids.update(
        (await session.execute(select(ResourceSkill.resource_id).distinct())).scalars().all()
    )
    overloads: list[dict[str, Any]] = []
    for resource_id in sorted(resource_ids, key=str):
        available = await available_hours(session, resource_id, on, scenario_id)
        demand = await demand_hours(session, resource_id, on, scenario_id)
        if available > ZERO and demand / available > Decimal("1.00"):
            overloads.append(
                {
                    "resource_id": resource_id,
                    "week_start": week,
                    "available": available,
                    "demand": demand,
                    "utilisation": demand / available,
                    "status": capacity_status(demand / available),
                }
            )
    return overloads


async def competency_shortage(
    session: AsyncSession, on: date, scenario_id: UUID | None = None
) -> list[dict[str, Any]]:
    """Competency shortages on the certified population (plan §9.2)."""
    week = week_start(on)
    shortages: list[dict[str, Any]] = []
    for competency in (await session.execute(select(Competency))).scalars().all():
        certified_ids = await eligible_resources(session, on, competency.id)
        if not certified_ids:
            continue
        shortage_demand = ZERO
        certified_capacity = ZERO
        for resource_id in certified_ids:
            shortage_demand += await demand_hours(session, resource_id, on, scenario_id)
            certified_capacity += await available_hours(session, resource_id, on, scenario_id)
        if certified_capacity <= ZERO:
            continue
        if shortage_demand > certified_capacity:
            shortages.append(
                {
                    "competency_id": competency.id,
                    "competency_name": competency.name,
                    "week_start": week,
                    "certified_resources": len(certified_ids),
                    "demand": shortage_demand,
                    "available": certified_capacity,
                    "utilisation": shortage_demand / certified_capacity,
                }
            )
    return shortages
