"""Capacity & what-if API (plan §10, Phase 6, T6.7).

Endpoints: capacity heatmap, conflict view with impact cascade, optimiser options,
and the scenario management endpoints (list/create/changes/promote/metrics).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.core.errors import AppError
from eil.modules.capacity import engine, optimiser, whatif
from eil.modules.capacity.analysis import impact_analysis
from eil.modules.capacity.models import ResourceSkill
from eil.modules.capacity.schemas import (
    CapacityConflictRead,
    CapacityHeatmapRead,
    ConflictAffectedRead,
    HeatmapResourceRead,
    HeatmapWeekRead,
    OptimiserAllocationRead,
    OptimiserDeltasRead,
    OptimiserOptionRead,
    ScenarioChangeCreate,
    ScenarioChangeRead,
    ScenarioCreate,
    ScenarioMetricsRead,
    ScenarioPromoteRequest,
    ScenarioRead,
)
from eil.modules.execution.models import Allocation, WorkItem, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import ALLOCATION_MANAGE, SCENARIO_PROMOTE, WORK_VIEW

router = APIRouter(tags=["capacity"])

CtxView = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
CtxManage = Annotated[PermissionContext, Depends(require_permission(ALLOCATION_MANAGE))]
CtxPromote = Annotated[PermissionContext, Depends(require_permission(SCENARIO_PROMOTE))]
Db = Annotated[AsyncSession, Depends(get_db)]


async def _resource_pool(session: AsyncSession) -> list[UUID]:
    ids: set[UUID] = set()
    ids.update((await session.execute(select(Allocation.resource_id))).scalars().all())
    ids.update((await session.execute(select(ResourceSkill.resource_id))).scalars().all())
    return sorted(ids, key=str)


async def _horizon(session: AsyncSession) -> tuple[date, date]:
    starts: list[date] = []
    ends: list[date] = []
    rows = (
        await session.execute(
            select(Allocation.start_date, Allocation.end_date).where(
                Allocation.scenario_id.is_(None), Allocation.hours_per_week.isnot(None)
            )
        )
    ).all()
    for row in rows:
        if row[0] is not None and row[1] is not None:
            starts.append(row[0])
            ends.append(row[1])
    task_rows = (
        await session.execute(
            select(WorkItem.planned_start, WorkItem.planned_end).where(
                WorkItem.type == WorkType.TASK,
                WorkItem.planned_start.isnot(None),
                WorkItem.planned_end.isnot(None),
            )
        )
    ).all()
    for task_row in task_rows:
        if task_row[0] is not None and task_row[1] is not None:
            starts.append(task_row[0])
            ends.append(task_row[1])
    if starts and ends:
        return min(starts), max(ends)
    return date.today(), date.today()


def _resource_name(resource_id: UUID, users: dict[UUID, str]) -> str:
    return users.get(resource_id, "resource")


@router.get("/capacity/heatmap", response_model=CapacityHeatmapRead)
async def capacity_heatmap(ctx: CtxView, session: Db) -> CapacityHeatmapRead:
    """Capacity heatmap: resources x weeks with utilisation/status (plan §10, T6.7)."""
    resources = await _resource_pool(session)
    horizon_start, horizon_end = await _horizon(session)
    weeks = sorted(
        {engine.week_start(day) for day in engine.days_between(horizon_start, horizon_end)}
    )
    users = dict((await session.execute(select(User.id, User.name))).all())
    rows: list[HeatmapResourceRead] = []
    for resource_id in resources:
        resource_name = _resource_name(resource_id, users)
        weeks_read: list[HeatmapWeekRead] = []
        for week in weeks:
            available = await engine.available_hours(session, resource_id, week)
            demand = await engine.demand_hours(session, resource_id, week)
            utilisation = await engine.utilisation(session, resource_id, week)
            weeks_read.append(
                HeatmapWeekRead(
                    week_start=week,
                    available=available,
                    demand=demand,
                    utilisation=utilisation,
                    status=engine.capacity_status(utilisation),
                )
            )
        rows.append(
            HeatmapResourceRead(
                resource_id=resource_id, resource_name=resource_name, weeks=weeks_read
            )
        )
    return CapacityHeatmapRead(resources=rows)


@router.get("/capacity/conflicts", response_model=list[CapacityConflictRead])
async def capacity_conflicts(ctx: CtxView, session: Db) -> list[CapacityConflictRead]:
    """Conflict view: overloads with the impacted commitments/projects/objectives."""
    overloads = await engine.detect_overloads(session, date.today())
    analysis = await impact_analysis(session, ctx, overloads)
    return [
        CapacityConflictRead(
            resource_id=row["resource_id"],
            week_start=row["week_start"],
            utilisation=row["utilisation"],
            status=row["status"],
            affected=[
                ConflictAffectedRead(
                    id=item["id"],
                    type=item["type"],
                    title=item["title"],
                    depth=item["depth"],
                    criticality=item["criticality"],
                )
                for item in row["affected"]
            ],
        )
        for row in analysis
    ]


@router.post("/capacity/optimise", response_model=list[OptimiserOptionRead])
async def capacity_optimise(ctx: CtxManage, session: Db) -> list[OptimiserOptionRead]:
    """Optimiser options across the four strategies (plan §9.3)."""
    options = await optimiser.optimise(session)
    return [
        OptimiserOptionRead(
            strategy=option["strategy"],
            option_index=option["option_index"],
            allocations=[
                OptimiserAllocationRead(
                    task_id=row["task_id"],
                    resource_id=row["resource_id"],
                    week_start=row["week"],
                    hours=row["hours"],
                )
                for row in option["allocations"]
            ],
            deltas=OptimiserDeltasRead(
                unmet_hours=option["deltas"]["unmet_hours"],
                overload_hours=option["deltas"]["overload_hours"],
                reassignment_hours=option["deltas"]["reassignment_hours"],
                skill_gap_hours=option["deltas"]["skill_gap_hours"],
                delayed_commitments=option["deltas"]["delayed_commitments"],
            ),
        )
        for option in options
    ]


@router.get("/scenarios", response_model=list[ScenarioRead])
async def list_scenarios(ctx: CtxView, session: Db) -> list[ScenarioRead]:
    rows = (
        (await session.execute(select(whatif.Scenario).order_by(whatif.Scenario.created_at.desc())))
        .scalars()
        .all()
    )
    return [ScenarioRead.model_validate(row) for row in rows]


@router.post("/scenarios", response_model=ScenarioRead, status_code=201)
async def create_scenario_endpoint(
    ctx: CtxManage, session: Db, payload: ScenarioCreate
) -> ScenarioRead:
    scenario = await whatif.create_scenario(
        session,
        name=payload.name,
        author_id=ctx.user.id,
        description=payload.description,
        expires_at=payload.expires_at,
    )
    await session.commit()
    return ScenarioRead.model_validate(scenario)


@router.post("/scenarios/{scenario_id}/changes", response_model=ScenarioChangeRead)
async def scenario_change_endpoint(
    scenario_id: UUID, ctx: CtxManage, session: Db, payload: ScenarioChangeCreate
) -> ScenarioChangeRead:
    change = await whatif.add_scenario_change(
        session,
        scenario_id,
        payload=payload.payload,
        allocation_id=payload.allocation_id,
        work_item_id=payload.work_item_id,
        reason=payload.reason,
    )
    await session.commit()
    return ScenarioChangeRead.model_validate(change)


@router.post("/scenarios/{scenario_id}/promote", response_model=ScenarioRead)
async def promote_scenario_endpoint(
    scenario_id: UUID, ctx: CtxPromote, session: Db, payload: ScenarioPromoteRequest
) -> ScenarioRead:
    """Promote a scenario through the overlay (SoD-6: approver != author)."""
    scenario = await whatif._get_scenario(session, scenario_id)
    if scenario.author_id == payload.approver_id:
        raise AppError(
            403,
            "sod_violation",
            "SOD-6 violation",
            "Scenario promotion requires approval by someone other than the scenario author.",
        )
    scenario = await whatif.promote_scenario(
        session, ctx, scenario_id, approver_id=payload.approver_id
    )
    await session.commit()
    return ScenarioRead.model_validate(scenario)


@router.get("/scenarios/{scenario_id}/metrics", response_model=ScenarioMetricsRead)
async def scenario_metrics_endpoint(
    ctx: CtxView, session: Db, scenario_id: UUID
) -> ScenarioMetricsRead:
    return ScenarioMetricsRead(**(await whatif.scenario_metrics(session, scenario_id)))
