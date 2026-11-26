"""What-if scenario engine (plan §9.4, Phase 6, T6.6).

A ``Scenario`` is an overlay of ``ScenarioChange`` rows (allocation edits, date
shifts, priority changes) over the baseline — the baseline is never copied or
mutated. Engines read through the overlay via ``scenario_id``
(:func:`eil.modules.capacity.engine.demand_hours`).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.audit.service import record_audit
from eil.modules.capacity import engine
from eil.modules.capacity.models import Scenario, ScenarioChange
from eil.modules.execution.models import Allocation, WorkItem, WorkType
from eil.modules.graph.cache import graph_cache
from eil.modules.identity.rbac import PermissionContext

ZERO = engine.ZERO


def _jsonable(value: Any) -> Any:
    """Coerce payload values to JSON-safe primitives for the ``payload`` column."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


async def _get_scenario(session: AsyncSession, scenario_id: UUID) -> Scenario:
    scenario = (
        (await session.execute(select(Scenario).where(Scenario.id == scenario_id)))
        .scalars()
        .first()
    )
    if scenario is None:
        raise AppError(404, "not_found", "Not found", "Scenario not found.")
    return scenario


async def create_scenario(
    session: AsyncSession,
    *,
    name: str,
    author_id: UUID,
    description: str | None = None,
    expires_at: date | None = None,
) -> Scenario:
    scenario = Scenario(
        name=name, description=description, author_id=author_id, expires_at=expires_at
    )
    session.add(scenario)
    await session.commit()
    return scenario


async def add_scenario_change(
    session: AsyncSession,
    scenario_id: UUID,
    *,
    payload: dict[str, Any],
    allocation_id: UUID | None = None,
    work_item_id: UUID | None = None,
    reason: str | None = None,
) -> ScenarioChange:
    await _get_scenario(session, scenario_id)
    change = ScenarioChange(
        scenario_id=scenario_id,
        allocation_id=allocation_id,
        work_item_id=work_item_id,
        payload={key: _jsonable(value) for key, value in payload.items()},
        reason=reason,
    )
    session.add(change)
    await session.commit()
    return change


async def _apply_priority_changes(session: AsyncSession, changes: Any) -> list[WorkItem]:
    applied: list[WorkItem] = []
    for change in changes:
        if change.work_item_id is None:
            continue
        payload = change.payload or {}
        if payload.get("priority_score") is None:
            continue
        item = (
            (await session.execute(select(WorkItem).where(WorkItem.id == change.work_item_id)))
            .scalars()
            .first()
        )
        if item is not None:
            item.priority_score = engine._dec(payload["priority_score"])
            applied.append(item)
    return applied


async def promote_scenario(
    session: AsyncSession,
    ctx: PermissionContext,
    scenario_id: UUID,
    *,
    approver_id: UUID | None = None,
) -> Scenario:
    """Apply the scenario overlay to the baseline: edited allocations updated in
    place, new allocations created, priority changes applied (plan §9.4)."""
    scenario = await _get_scenario(session, scenario_id)
    if scenario.promoted:
        raise AppError(409, "conflict", "Conflict", "Scenario is already promoted.")
    changes = await engine.scenario_changes_by_allocation(session, scenario_id)
    for change in changes.values():
        if change.allocation_id is not None:
            row = (
                (
                    await session.execute(
                        select(Allocation).where(Allocation.id == change.allocation_id)
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                continue
            payload = change.payload or {}
            for field, converter in (
                ("hours_per_week", engine._dec),
                ("start_date", engine._as_date),
                ("end_date", engine._as_date),
            ):
                if payload.get(field) is not None:
                    setattr(row, field, converter(payload[field]))
            if payload.get("locked") is not None:
                row.locked = bool(payload["locked"])
            continue
        payload = change.payload or {}
        start = engine._as_date(payload.get("start_date"))
        end = engine._as_date(payload.get("end_date"))
        resource_id = engine._as_uuid(payload.get("resource_id"))
        if start is None or end is None or resource_id is None:
            continue
        allocation = Allocation(
            resource_id=resource_id,
            work_item_id=engine._as_uuid(payload.get("work_item_id")),
            kind=str(payload.get("kind") or "project"),
            start_date=start,
            end_date=end,
            hours_total=engine._dec(payload.get("hours_total")) or None,
            hours_per_week=engine._dec(payload.get("hours_per_week")) or None,
            locked=bool(payload.get("locked")),
        )
        session.add(allocation)
        await session.flush()
        change.allocation_id = allocation.id
    await _apply_priority_changes(session, changes.values())
    scenario.promoted = True
    scenario.approved_by_id = approver_id
    scenario.promoted_at = utcnow()
    await session.commit()
    graph_cache.invalidate()
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="scenario.promoted",
        entity_type="scenario",
        entity_id=scenario.id,
        before={"promoted": False},
        after={
            "promoted": True,
            "approved_by": str(approver_id) if approver_id else None,
            "changes": len(changes),
        },
        reason=f"Scenario '{scenario.name}' promoted through the overlay.",
    )
    await session.commit()
    return scenario


async def scenario_metrics(session: AsyncSession, scenario_id: UUID) -> dict[str, Any]:
    """Scenario metrics (plan §9.4): overload hours, red weeks, delayed
    commitments and a cost proxy over the scenario horizon."""
    changes = await engine.scenario_changes_by_allocation(session, scenario_id)
    resource_ids: set[UUID] = set()
    weeks: set[date] = set()
    horizon_start: date | None = None
    horizon_end: date | None = None
    for change in changes.values():
        if change.allocation_id is None:
            payload = change.payload or {}
            resource_id = engine._as_uuid(payload.get("resource_id"))
            if resource_id is not None:
                resource_ids.add(resource_id)
            start = engine._as_date(payload.get("start_date"))
            end = engine._as_date(payload.get("end_date"))
            if start is not None and end is not None:
                weeks.update({engine.week_start(day) for day in engine.days_between(start, end)})
                horizon_start = start if horizon_start is None else min(horizon_start, start)
                horizon_end = end if horizon_end is None else max(horizon_end, end)
        else:
            row = (
                (
                    await session.execute(
                        select(Allocation).where(Allocation.id == change.allocation_id)
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                resource_ids.add(row.resource_id)
                if row.start_date is not None:
                    weeks.add(engine.week_start(row.start_date))
                    horizon_start = (
                        row.start_date
                        if horizon_start is None
                        else min(horizon_start, row.start_date)
                    )
                if row.end_date is not None:
                    horizon_end = (
                        row.end_date if horizon_end is None else max(horizon_end, row.end_date)
                    )

    overload_hours = ZERO
    red_weeks: set[tuple[UUID, date]] = set()
    for week in sorted(weeks):
        for resource_id in sorted(resource_ids, key=str):
            util = await engine.utilisation(session, resource_id, week, scenario_id)
            available = await engine.available_hours(session, resource_id, week, scenario_id)
            if util is not None and util > Decimal("1.00"):
                overload_hours += available * (util - Decimal("1.00"))
                red_weeks.add((resource_id, week))

    delayed_commitments = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type == WorkType.COMMITMENT,
                    WorkItem.baseline_end.isnot(None),
                    WorkItem.forecast_end.isnot(None),
                    WorkItem.forecast_end > WorkItem.baseline_end,
                )
            )
        )
        .scalars()
        .all()
    )
    cost_proxy = ZERO
    if horizon_start is not None and horizon_end is not None:
        for row in (
            (
                await session.execute(
                    select(Allocation).where(
                        Allocation.start_date <= horizon_end,
                        Allocation.end_date >= horizon_start,
                        Allocation.hours_per_week.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            cost_proxy += engine._dec(row.hours_per_week)

    return {
        "scenario_id": scenario_id,
        "overload_hours": overload_hours,
        "red_weeks": len(red_weeks),
        "delayed_commitments": len(delayed_commitments),
        "cost_proxy": cost_proxy,
    }


async def expire_scenarios(session: AsyncSession, on: date | None = None) -> list[Scenario]:
    """Mark scenarios whose ``expires_at`` has passed (plan §9.4)."""
    on = on or date.today()
    rows = (
        (
            await session.execute(
                select(Scenario).where(
                    Scenario.expires_at.isnot(None),
                    Scenario.expires_at <= on,
                    Scenario.expired.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.expired = True
    await session.commit()
    return list(rows)
