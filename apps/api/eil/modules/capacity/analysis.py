"""Impact analysis for capacity conflicts (plan §9.2, Phase 6, T6.4).

For each overload conflict, the affected commitments/projects/objectives are
listed via the graph downstream-impact query with criticality weighting
(``strongest_path_weight`` x the overload's utilisation).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.modules.capacity import engine
from eil.modules.capacity.engine import ZERO
from eil.modules.execution.models import Allocation, WorkItem, WorkType
from eil.modules.graph.service import downstream_impact
from eil.modules.identity.rbac import PermissionContext

IMPACTED_TYPES = (WorkType.COMMITMENT, WorkType.PROJECT, WorkType.OBJECTIVE)


async def impact_analysis(
    session: AsyncSession, ctx: PermissionContext, overloads: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Affected commitments/projects/objectives per overload (plan §9.2)."""
    results: list[dict[str, Any]] = []
    for overload in overloads:
        week = overload["week_start"]
        resource_id = overload["resource_id"]
        roots: set[UUID] = set()
        for row in (
            (
                await session.execute(
                    select(Allocation).where(
                        Allocation.resource_id == resource_id,
                        Allocation.start_date <= week + timedelta(days=6),
                        Allocation.end_date >= week,
                        Allocation.work_item_id.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        ):
            if row.work_item_id is not None:
                roots.add(row.work_item_id)
        for task_id in (
            (
                await session.execute(
                    select(WorkItem.id).where(
                        WorkItem.owner_id == resource_id,
                        WorkItem.type == WorkType.TASK,
                        WorkItem.planned_start.isnot(None),
                        WorkItem.planned_end.isnot(None),
                        WorkItem.planned_start <= week + timedelta(days=6),
                        WorkItem.planned_end >= week,
                    )
                )
            )
            .scalars()
            .all()
        ):
            roots.add(task_id)
        weight = overload.get("utilisation") or ZERO
        affected: dict[UUID, dict[str, Any]] = {}
        for root_id in sorted(roots, key=str):
            try:
                impact = await downstream_impact(session, ctx, root_id)
            except AppError:
                continue
            for item in impact.items:
                if item.type not in IMPACTED_TYPES:
                    continue
                criticality = (item.strongest_path_weight or ZERO) * weight
                existing = affected.get(item.id)
                if existing is None or criticality > existing["criticality"]:
                    affected[item.id] = {
                        "id": item.id,
                        "type": str(item.type),
                        "title": item.title,
                        "depth": item.depth,
                        "criticality": criticality,
                    }
        util = overload.get("utilisation")
        ordered = sorted(
            affected.values(), key=lambda row: (-row["depth"], -float(row["criticality"]))
        )
        results.append(
            {
                "resource_id": resource_id,
                "week_start": week,
                "utilisation": util,
                "status": engine.capacity_status(util),
                "affected": ordered,
            }
        )
    return results
