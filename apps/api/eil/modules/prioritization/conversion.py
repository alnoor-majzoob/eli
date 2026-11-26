"""Demand → delivery conversion (plan §10, Phase 5, T5.4).

On demand approval: create a ``project`` from a template — WBS-style children,
default benefits (`realizes` links) — carrying the demand's alignment links and
the deterministic score onto the project's attributes.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.modules.audit.service import record_audit
from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.graph.cache import graph_cache
from eil.modules.identity.rbac import PermissionContext
from eil.modules.prioritization.models import Score
from eil.modules.prioritization.service import compute_score

DEFAULT_DELIVERY_BENEFITS: tuple[tuple[str, str], ...] = (
    ("On-time delivery", "On-time delivery of the initiative against baseline dates."),
    ("HSSE performance", "Maintain or improve the site HSSE performance standard."),
)


async def convert_demand_to_delivery(
    session: AsyncSession, ctx: PermissionContext, demand_id: Any
) -> WorkItem:
    demand = (
        (await session.execute(select(WorkItem).where(WorkItem.id == demand_id))).scalars().first()
    )
    if demand is None:
        raise AppError(404, "not_found", "Not found", "Demand not found.")
    if demand.type != WorkType.DEMAND:
        raise AppError(422, "validation_error", "Validation error", "Item is not a demand.")

    score = (
        (await session.execute(select(Score).where(Score.work_item_id == demand.id)))
        .scalars()
        .first()
    )
    if score is None:
        score = await compute_score(session, demand)

    alignment_links = (
        (
            await session.execute(
                select(WorkLink).where(
                    WorkLink.src_id == demand.id,
                    WorkLink.link_type == "aligns_to",
                    WorkLink.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )

    project = WorkItem(
        type=WorkType.PROJECT,
        title=f"Delivery: {demand.title}",
        description=demand.description,
        status="draft",
        origin="native",
        attributes={
            "source_demand_id": str(demand.id),
            "calculated_score": float(score.score),
            "tier": score.tier,
        },
        created_by=ctx.user.id,
    )
    session.add(project)
    await session.flush()
    for link in alignment_links:
        session.add(
            WorkLink(
                src_id=project.id,
                dst_id=link.dst_id,
                link_type="aligns_to",
                origin="system",
                status="active",
                weight=1,
            )
        )
    for benefit_title, benefit_description in DEFAULT_DELIVERY_BENEFITS:
        benefit = WorkItem(
            type=WorkType.BENEFIT,
            title=benefit_title,
            description=benefit_description,
            status="active",
            origin="native",
            attributes={"source": "demand-conversion", "source_demand_id": str(demand.id)},
            created_by=ctx.user.id,
        )
        session.add(benefit)
        await session.flush()
        session.add(
            WorkLink(
                src_id=project.id,
                dst_id=benefit.id,
                link_type="realizes",
                origin="system",
                status="active",
                weight=1,
            )
        )

    await session.commit()
    graph_cache.invalidate()
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="demand.converted_to_project",
        entity_type="work_item",
        entity_id=project.id,
        org_unit_id=project.org_unit_id,
        reason=f"Demand approved: {demand.title} → project {project.title}.",
        after={"source_demand_id": str(demand.id), "tier": score.tier},
    )
    await session.commit()
    return project
