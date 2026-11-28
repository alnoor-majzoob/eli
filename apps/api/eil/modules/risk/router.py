"""Risk & escalation API (plan §10, Phase 7, T7.8).

- ``GET /risk/radar`` — portfolio risk rows: confidence x impact (plan §9.5).
- ``GET /escalations`` — management escalation inbox.
- ``PATCH /escalations/{id}/acknowledge`` — acknowledgement tracking.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.execution.models import WorkItem, WorkItemStatus
from eil.modules.graph.service import downstream_impact
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.risk.models import Escalation
from eil.modules.risk.schemas import EscalationRead, RiskRadarRow
from eil.modules.risk.service import PARENT_TYPES
from eil.modules.seed_data import WORK_EDIT, WORK_VIEW

router = APIRouter(tags=["risk"])

CtxView = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
CtxWrite = Annotated[PermissionContext, Depends(require_permission(WORK_EDIT))]
Db = Annotated[AsyncSession, Depends(get_db)]


async def _impact_weight(session: AsyncSession, ctx: PermissionContext, item_id: UUID) -> Decimal:
    try:
        impact = await downstream_impact(session, ctx, item_id)
    except AppError:
        return Decimal("0")
    total = Decimal("0")
    for row in impact.items:
        weight = row.strongest_path_weight
        total += weight if weight is not None else Decimal("1")
    return total


@router.get("/risk/radar", response_model=list[RiskRadarRow])
async def risk_radar(ctx: CtxView, session: Db) -> list[RiskRadarRow]:
    """Radar rows: delivery confidence x impact for open parent items (plan §9.5)."""
    radar_stmt = select(WorkItem).where(
        WorkItem.type.in_(PARENT_TYPES),
        WorkItem.status.notin_((WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)),
    )
    if ctx.scope == "own_org":
        radar_stmt = radar_stmt.where(WorkItem.org_unit_id == ctx.user.org_unit_id)
    items = (await session.execute(radar_stmt)).scalars().all()
    rows = []
    for item in items:
        confidence = item.delivery_confidence or Decimal("0")
        impact = await _impact_weight(session, ctx, item.id)
        rows.append(
            RiskRadarRow(
                item_id=item.id,
                title=item.title,
                type=str(item.type),
                status=str(item.status),
                confidence=float(confidence),
                impact=float(impact),
                risk_score=float(confidence * impact),
            )
        )
    return rows


@router.get("/escalations", response_model=list[EscalationRead])
async def list_escalations(
    ctx: CtxView, session: Db, status: str | None = None
) -> list[EscalationRead]:
    filters: list = []
    if status == "open":
        filters.append(Escalation.acknowledged_at.is_(None))
    elif status:
        filters.append(Escalation.status == status)
    esc_stmt = select(Escalation).where(*filters).order_by(Escalation.due_at)
    if ctx.scope == "own_org":
        esc_stmt = esc_stmt.join(WorkItem, WorkItem.id == Escalation.work_item_id).where(
            WorkItem.org_unit_id == ctx.user.org_unit_id
        )
    rows = (await session.execute(esc_stmt)).scalars().all()
    return [EscalationRead.model_validate(row) for row in rows]


@router.patch("/escalations/{escalation_id}/acknowledge", response_model=EscalationRead)
async def acknowledge_escalation(escalation_id: UUID, ctx: CtxWrite, session: Db) -> EscalationRead:
    """Acknowledgement tracking (plan §9.6). Requires work.edit + org scope."""
    row = (
        (await session.execute(select(Escalation).where(Escalation.id == escalation_id)))
        .scalars()
        .first()
    )
    if row is None:
        raise AppError(404, "not_found", "Not found", "Escalation not found.")
    if ctx.scope == "own_org":
        org = None
        if row.work_item_id is not None:
            org = (
                await session.execute(
                    select(WorkItem.org_unit_id).where(WorkItem.id == row.work_item_id)
                )
            ).scalar_one_or_none()
        if org != ctx.user.org_unit_id:
            raise AppError(404, "not_found", "Not found", "Escalation not found.")
    if row.status == "closed":
        raise AppError(409, "conflict", "Conflict", "Escalation is closed.")
    if row.acknowledged_at is None:
        row.acknowledged_by = ctx.user.id
        row.acknowledged_at = utcnow()
    row.status = "acknowledged"
    await session.commit()
    return EscalationRead.model_validate(row)
