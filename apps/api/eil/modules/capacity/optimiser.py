"""Recommendation optimiser (plan §9.3, Phase 6, T6.5).

CP-SAT optimiser: assigns eligible tasks to resources over the task windows,
respecting weekly capacity (``available_hours`` minus baseline demand) and
returning quantified deltas per strategy (reassign / resequence / reprioritise /
augment — plan §9.3).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.capacity import engine
from eil.modules.capacity.models import Certification, ResourceContract, ResourceSkill
from eil.modules.execution.models import Allocation, WorkItem, WorkItemStatus, WorkType

ZERO = engine.ZERO

STRATEGY_WEIGHTS: dict[str, dict[str, Decimal]] = {
    "reassign": {
        "reassign": Decimal("2.0"),
        "unmet": Decimal("1.0"),
        "skill_gap": Decimal("1.0"),
    },
    "resequence": {"unmet": Decimal("0.5"), "overload": Decimal("0.5")},
    "reprioritise": {
        "unmet": Decimal("1.0"),
        "skill_gap": Decimal("1.0"),
        "overload": Decimal("1.5"),
    },
    "augment": {"unmet": Decimal("0.2"), "skill_gap": Decimal("0.5"), "overload": Decimal("2.0")},
}


def _task_hours(task: WorkItem) -> Decimal:
    effort = (task.attributes or {}).get("effort_hours")
    if effort:
        return engine._dec(effort)
    if task.planned_start is not None and task.planned_end is not None:
        return Decimal((task.planned_end - task.planned_start).days + 1)
    return ZERO


async def _scope_tasks(session: AsyncSession) -> list[WorkItem]:
    return list(
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type == WorkType.TASK,
                    WorkItem.status.notin_((WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)),
                    WorkItem.planned_start.isnot(None),
                    WorkItem.planned_end.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )


async def _resource_pool(session: AsyncSession) -> list[UUID]:
    ids: set[UUID] = set()
    ids.update((await session.execute(select(Allocation.resource_id))).scalars().all())
    ids.update((await session.execute(select(ResourceSkill.resource_id))).scalars().all())
    ids.update((await session.execute(select(ResourceContract.resource_id))).scalars().all())
    return sorted(ids, key=str)


def _task_weeks(task: WorkItem) -> list[date]:
    if task.planned_start is None or task.planned_end is None:
        return []
    return sorted(
        {
            engine.week_start(day)
            for day in engine.days_between(task.planned_start, task.planned_end)
        }
    )


def _requirements(task: WorkItem) -> tuple[list[UUID], int | None]:
    attrs = task.attributes or {}
    raw = [engine._as_uuid(v) for v in (attrs.get("required_competencies") or [])]
    competencies: list[UUID] = [c for c in raw if c is not None]
    min_proficiency = attrs.get("min_proficiency")
    return competencies, int(min_proficiency) if min_proficiency else None


async def _eligible(session: AsyncSession, task: WorkItem, resources: list[UUID]) -> set[UUID]:
    """Resources satisfying the task's competency/certification requirements."""
    competencies, min_proficiency = _requirements(task)
    if not competencies:
        return set(resources)
    on = task.planned_start or date.today()
    eligible: set[UUID] | None = None
    for competency_id in competencies:
        current = set(await engine.eligible_resources(session, on, competency_id, min_proficiency))
        eligible = current if eligible is None else eligible & current
    return eligible or set()


async def _original_resource(session: AsyncSession, task_id: UUID) -> UUID | None:
    row = (
        (
            await session.execute(
                select(Allocation).where(
                    Allocation.work_item_id == task_id, Allocation.scenario_id.is_(None)
                )
            )
        )
        .scalars()
        .first()
    )
    return row.resource_id if row is not None else None


async def _has_skill(
    session: AsyncSession, resource_id: UUID, competency_id: UUID, min_proficiency: int | None
) -> bool:
    skills = (
        (
            await session.execute(
                select(ResourceSkill).where(
                    ResourceSkill.resource_id == resource_id,
                    ResourceSkill.competency_id == competency_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not any(s.proficiency >= (min_proficiency or 1) for s in skills):
        return False
    certs = (
        (
            await session.execute(
                select(Certification).where(
                    Certification.resource_id == resource_id,
                    Certification.competency_id == competency_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return any(engine.is_certification_valid(cert, date.today()) for cert in certs)


async def _build_model(
    session: AsyncSession,
    tasks: list[WorkItem],
    resources: list[UUID],
    horizon_weeks: list[date],
    baseline_demand: dict[tuple[UUID, date], Decimal],
    available: dict[tuple[UUID, date], Decimal],
) -> tuple[Any, dict[tuple[UUID, UUID, date], Any], dict[UUID, UUID | None]]:
    model: Any = cp_model.CpModel()
    x: dict[tuple[UUID, UUID, date], Any] = {}
    original_resources: dict[UUID, UUID | None] = {}
    for task in tasks:
        hours = int(_task_hours(task))
        if hours <= 0:
            continue
        original_resources[task.id] = await _original_resource(session, task.id)
        eligible = await _eligible(session, task, resources)
        keys: list[Any] = []
        for resource_id in resources:
            if resource_id not in eligible:
                continue
            for week in _task_weeks(task):
                var = model.NewIntVar(0, hours, f"x_{task.id}_{resource_id}_{week.isoformat()}")
                x[(task.id, resource_id, week)] = var
                keys.append(var)
        if not keys:
            continue
        model.Add(sum(keys) == hours)
    for resource_id in resources:
        for week in horizon_weeks:
            terms = [var for (task_id, r, w), var in x.items() if r == resource_id and w == week]
            if terms:
                capacity = max(
                    available[(resource_id, week)] - baseline_demand[(resource_id, week)], ZERO
                )
                model.Add(sum(terms) <= capacity)
    return model, x, original_resources


def _objective(
    x: dict[tuple[UUID, UUID, date], Any],
    original_resources: dict[UUID, UUID | None],
    weights: dict[str, Decimal],
) -> list[Any]:
    """Reassignment penalties per strategy (plan §9.3 objectives)."""
    weight = weights.get("reassign") or ZERO
    if not weight:
        return []
    return [
        weight * var
        for (task_id, resource_id, _), var in x.items()
        if (original := original_resources.get(task_id)) is not None and resource_id != original
    ]


async def optimise(session: AsyncSession, top_n: int = 4) -> list[dict[str, Any]]:
    """Return the top-N optimiser options across the four strategies (plan §9.3)."""
    tasks = await _scope_tasks(session)
    resources = await _resource_pool(session)
    if not tasks or not resources:
        return []
    horizon_start = min(task.planned_start for task in tasks if task.planned_start)
    horizon_end = max(task.planned_end for task in tasks if task.planned_end) or horizon_start
    horizon_weeks = sorted(
        {engine.week_start(d) for d in engine.days_between(horizon_start, horizon_end)}
    )

    baseline_demand: dict[tuple[UUID, date], Decimal] = defaultdict(lambda: ZERO)
    for row in (
        (
            await session.execute(
                select(Allocation).where(
                    Allocation.scenario_id.is_(None), Allocation.hours_per_week.isnot(None)
                )
            )
        )
        .scalars()
        .all()
    ):
        weeks = {engine.week_start(d) for d in engine.days_between(row.start_date, row.end_date)}
        for week in weeks:
            baseline_demand[(row.resource_id, week)] += engine._dec(row.hours_per_week)

    available: dict[tuple[UUID, date], Decimal] = {}
    for resource_id in resources:
        for week in horizon_weeks:
            available[(resource_id, week)] = await engine.available_hours(
                session, resource_id, week
            )

    options: list[dict[str, Any]] = []
    seen: set[frozenset] = set()
    for strategy, weights in STRATEGY_WEIGHTS.items():
        model, x, original_resources = await _build_model(
            session, tasks, resources, horizon_weeks, baseline_demand, available
        )
        if not x:
            continue
        objective_terms = _objective(x, original_resources, weights)
        if objective_terms:
            model.Minimize(sum(objective_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            continue
        solution = {
            key: Decimal(solver.Value(var)) for key, var in x.items() if solver.Value(var) > 0
        }
        deltas = await _deltas(
            session, tasks, resources, horizon_weeks, baseline_demand, solution, original_resources
        )
        signature = frozenset(solution)
        if signature in seen:
            continue
        seen.add(signature)
        allocations = [
            {
                "task_id": task_id,
                "resource_id": resource_id,
                "week": week,
                "hours": int(value),
            }
            for (task_id, resource_id, week), value in sorted(
                solution.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), kv[0][2])
            )
        ]
        options.append(
            {
                "strategy": strategy,
                "option_index": len(options) + 1,
                "allocations": allocations,
                "deltas": deltas,
            }
        )
        if len(options) >= top_n:
            break
    return options


async def _deltas(
    session: AsyncSession,
    tasks: list[WorkItem],
    resources: list[UUID],
    horizon_weeks: list[date],
    baseline_demand: dict[tuple[UUID, date], Decimal],
    solution: dict[tuple[UUID, UUID, date], Decimal],
    original_resources: dict[UUID, UUID | None],
) -> dict[str, Any]:
    demand: dict[tuple[UUID, date], Decimal] = defaultdict(lambda: ZERO)
    for (_task_id, resource_id, week), value in solution.items():
        demand[(resource_id, week)] += value
    unmet_hours = ZERO
    overload_hours = ZERO
    for resource_id in resources:
        for week in horizon_weeks:
            total = baseline_demand[(resource_id, week)] + demand[(resource_id, week)]
            available = await engine.available_hours(session, resource_id, week)
            unmet_hours += max(total - available, ZERO)
            util = total / available if available > ZERO else None
            if util is not None and util > Decimal("1.00"):
                overload_hours += available * (util - Decimal("1.00"))
    reassignment_hours = ZERO
    skill_gap_hours = ZERO
    assigned_by_task: dict[UUID, list[tuple[UUID, Decimal]]] = defaultdict(list)
    for (task_id, resource_id, _), value in solution.items():
        assigned_by_task[task_id].append((resource_id, value))
    for task in tasks:
        competencies, min_proficiency = _requirements(task)
        for resource_id, value in assigned_by_task.get(task.id, []):
            if (
                original := original_resources.get(task.id)
            ) is not None and resource_id != original:
                reassignment_hours += value
            if competencies:
                skill_ok = False
                for competency_id in competencies:
                    if await _has_skill(session, resource_id, competency_id, min_proficiency):
                        skill_ok = True
                        break
                if not skill_ok:
                    skill_gap_hours += value
    delayed_commitments = len(
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
    return {
        "unmet_hours": unmet_hours,
        "overload_hours": overload_hours,
        "reassignment_hours": reassignment_hours,
        "skill_gap_hours": skill_gap_hours,
        "delayed_commitments": delayed_commitments,
    }
