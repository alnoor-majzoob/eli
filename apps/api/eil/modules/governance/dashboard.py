"""Departmental dashboard counts and highlights."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.models import utcnow
from eil.modules.execution.models import WorkItem, WorkItemStatus, WorkType
from eil.modules.governance.models import Approval
from eil.modules.identity.rbac import PermissionContext

_OPEN_STATUSES = {
    WorkItemStatus.DRAFT,
    WorkItemStatus.SUBMITTED,
    WorkItemStatus.APPROVED,
    WorkItemStatus.ACTIVE,
    WorkItemStatus.ON_HOLD,
}


def _scoped(ctx: PermissionContext, stmt: Any) -> Any:
    if ctx.scope == "own_org":
        stmt = stmt.where(WorkItem.org_unit_id == ctx.user.org_unit_id)
    return stmt


def _rag_for(item: WorkItem, today: date) -> str:
    explicit = (item.attributes or {}).get("rag")
    if explicit in {"green", "amber", "red"}:
        return str(explicit)
    if item.planned_end is not None and item.planned_end < today and item.status in _OPEN_STATUSES:
        return "red"
    if item.delivery_confidence is not None:
        confidence = float(item.delivery_confidence)
        if confidence < 0.5:
            return "red"
        if confidence < 0.75:
            return "amber"
    return "green"


async def status_counts(session: AsyncSession, ctx: PermissionContext) -> dict[str, int]:
    stmt = _scoped(ctx, select(WorkItem.status, func.count().label("n")))
    rows = (await session.execute(stmt.group_by(WorkItem.status))).all()
    return {str(row.status): int(row.n) for row in rows}


async def type_counts(session: AsyncSession, ctx: PermissionContext) -> dict[str, int]:
    stmt = _scoped(ctx, select(WorkItem.type, func.count().label("n")))
    rows = (await session.execute(stmt.group_by(WorkItem.type))).all()
    return {str(row.type): int(row.n) for row in rows}


async def pending_demands(
    session: AsyncSession, ctx: PermissionContext, limit: int = 10
) -> list[WorkItem]:
    stmt = _scoped(
        ctx,
        select(WorkItem).where(
            WorkItem.type == WorkType.DEMAND, WorkItem.status == WorkItemStatus.SUBMITTED
        ),
    )
    stmt = stmt.order_by(WorkItem.created_at.desc(), WorkItem.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def recent_items(
    session: AsyncSession, ctx: PermissionContext, limit: int = 10
) -> list[WorkItem]:
    stmt = _scoped(ctx, select(WorkItem))
    stmt = stmt.order_by(WorkItem.updated_at.desc(), WorkItem.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def upcoming_milestones(
    session: AsyncSession, ctx: PermissionContext, days: int = 30, limit: int = 10
) -> list[WorkItem]:
    today = date.today()
    horizon = today + timedelta(days=days)
    stmt = _scoped(
        ctx,
        select(WorkItem).where(
            WorkItem.type == WorkType.MILESTONE,
            WorkItem.planned_end.is_not(None),
            WorkItem.planned_end >= today,
            WorkItem.planned_end <= horizon,
            WorkItem.status.in_(list(_OPEN_STATUSES)),
        ),
    )
    stmt = stmt.order_by(WorkItem.planned_end, WorkItem.id).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def overdue_count(session: AsyncSession, ctx: PermissionContext) -> int:
    stmt = _scoped(
        ctx,
        select(func.count())
        .select_from(WorkItem)
        .where(
            WorkItem.planned_end.is_not(None),
            WorkItem.planned_end < date.today(),
            WorkItem.status.in_(list(_OPEN_STATUSES)),
        ),
    )
    return int((await session.execute(stmt)).scalar_one())


async def rag_counts(session: AsyncSession, ctx: PermissionContext) -> dict[str, int]:
    stmt = _scoped(ctx, select(WorkItem))
    rows: list[WorkItem] = list((await session.execute(stmt)).scalars().all())
    today = date.today()
    counts = {"green": 0, "amber": 0, "red": 0}
    for item in rows:
        if item.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED}:
            continue
        counts[_rag_for(item, today)] += 1
    return counts


async def pending_approval_count(session: AsyncSession, ctx: PermissionContext) -> int:
    stmt = (
        select(func.count())
        .select_from(Approval)
        .join(WorkItem, WorkItem.id == Approval.work_item_id)
        .where(Approval.status == "pending")
    )
    if ctx.scope == "own_org":
        stmt = stmt.where(WorkItem.org_unit_id == ctx.user.org_unit_id)
    if "admin" not in ctx.roles:
        stmt = stmt.where(
            (Approval.approver_role.in_(ctx.roles)) | (Approval.delegated_to == ctx.user.id)
        )
    return int((await session.execute(stmt)).scalar_one())


async def dashboard_summary(session: AsyncSession, ctx: PermissionContext) -> dict[str, Any]:
    statuses = await status_counts(session, ctx)
    return {
        "as_of": utcnow(),
        "total": sum(statuses.values()),
        "statuses": statuses,
        "by_type": await type_counts(session, ctx),
        "rag": await rag_counts(session, ctx),
        "overdue": await overdue_count(session, ctx),
        "upcoming_milestones": await upcoming_milestones(session, ctx),
        "pending_approvals": await pending_approval_count(session, ctx),
        "pending_demands": await pending_demands(session, ctx),
        "recent_items": await recent_items(session, ctx),
    }
