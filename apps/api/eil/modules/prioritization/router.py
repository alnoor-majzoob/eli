"""Prioritisation board API (plan §10, Phase 5, T5.3).

Returns scored work items ranked by the deterministic score, with the tier,
calculated score, rationale and a cut-line flag (tier ≥ 3 — below the
funding/capacity cut-line at the current model).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.core.errors import AppError
from eil.modules.audit.service import record_audit
from eil.modules.execution.models import Allocation, WorkItem
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.prioritization.models import Score
from eil.modules.prioritization.schemas import (
    AllocationCreate,
    AllocationRead,
    AllocationUpdate,
    OverrideCreate,
    PrioritizedItemRead,
    ScoreOverrideRead,
)
from eil.modules.prioritization.service import apply_override
from eil.modules.seed_data import CONNECTOR_MANAGE, PRIORITY_OVERRIDE, WORK_VIEW

router = APIRouter(tags=["prioritization"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
CtxOverride = Annotated[PermissionContext, Depends(require_permission(PRIORITY_OVERRIDE))]
CtxAdmin = Annotated[PermissionContext, Depends(require_permission(CONNECTOR_MANAGE))]
Db = Annotated[AsyncSession, Depends(get_db)]

CUT_LINE_TIER = 3  # items at tier ≥ 3 are below the funding cut-line.


@router.get("/prioritization", response_model=list[PrioritizedItemRead])
async def prioritized_items(
    ctx: CtxRead, session: Db, limit: int = 200
) -> list[PrioritizedItemRead]:
    rows = (
        await session.execute(
            select(Score, WorkItem)
            .join(WorkItem, WorkItem.id == Score.work_item_id)
            .order_by(Score.score.desc(), Score.computed_at.desc(), Score.id.desc())
            .limit(limit)
        )
    ).all()
    items = []
    for score, work_item in rows:
        items.append(
            PrioritizedItemRead(
                id=work_item.id,
                type=work_item.type,
                title=work_item.title,
                tier=score.tier,
                score=score.score,
                rationale=score.rationale,
                model_id=score.model_id,
                computed_at=score.computed_at,
                in_cut_line=score.tier >= CUT_LINE_TIER,
            )
        )
    return items


@router.post("/prioritization/{item_id}/override", response_model=ScoreOverrideRead)
async def prioritization_override(
    item_id: UUID, ctx: CtxOverride, session: Db, payload: OverrideCreate
) -> ScoreOverrideRead:
    """Apply a human-approved priority override (plan §10, Phase 5, T5.3).

    SoD-2 (plan §13.2): the override approver must differ from the requester;
    every denial is audited. The original calculated tier is preserved on the
    override; the board shows the new tier.
    """
    approver = (
        (await session.execute(select(User).where(User.id == payload.approver_id)))
        .scalars()
        .first()
    )
    if approver is None or not approver.is_active:
        raise AppError(422, "validation_error", "Validation error", "Approver not found.")
    if payload.approver_id == ctx.user.id:
        await record_audit(
            session,
            actor_id=ctx.principal.subject,
            actor_type="user",
            action="priority.override_denied",
            entity_type="work_item",
            entity_id=item_id,
            org_unit_id=ctx.user.org_unit_id,
            reason="SOD-2: the priority override approver equals the requester.",
        )
        await session.commit()
        raise AppError(
            403,
            "sod_violation",
            "SOD-2 violation",
            "The approver of a priority override must differ from the requester.",
        )
    override = await apply_override(
        session, ctx, item_id, payload.tier, payload.justification, payload.approver_id
    )
    await session.commit()
    return ScoreOverrideRead.model_validate(override)


@router.get("/allocations", response_model=list[AllocationRead])
async def allocations_list(
    ctx: CtxAdmin,
    session: Db,
    work_item_id: UUID | None = None,
) -> list[AllocationRead]:
    stmt = select(Allocation)
    if work_item_id is not None:
        stmt = stmt.where(Allocation.work_item_id == work_item_id)
    rows = (
        (await session.execute(stmt.order_by(Allocation.start_date, Allocation.id))).scalars().all()
    )
    return [AllocationRead.model_validate(row) for row in rows]


@router.post("/allocations", response_model=AllocationRead, status_code=201)
async def allocation_create(
    ctx: CtxAdmin, session: Db, payload: AllocationCreate
) -> AllocationRead:
    allocation = Allocation(
        resource_id=payload.resource_id,
        work_item_id=payload.work_item_id,
        kind=payload.kind,
        start_date=payload.start_date,
        end_date=payload.end_date,
        hours_total=payload.hours_total,
        hours_per_week=payload.hours_per_week,
        locked=payload.locked,
    )
    session.add(allocation)
    await session.commit()
    await session.refresh(allocation)
    return AllocationRead.model_validate(allocation)


@router.patch("/allocations/{allocation_id}", response_model=AllocationRead)
async def allocation_update(
    allocation_id: UUID, ctx: CtxAdmin, session: Db, payload: AllocationUpdate
) -> AllocationRead:
    allocation = (
        (await session.execute(select(Allocation).where(Allocation.id == allocation_id)))
        .scalars()
        .first()
    )
    if allocation is None:
        from eil.core.errors import AppError

        raise AppError(404, "not_found", "Not found", "Allocation not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(allocation, field, value)
    session.add(allocation)
    await session.commit()
    await session.refresh(allocation)
    return AllocationRead.model_validate(allocation)
