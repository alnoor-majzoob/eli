"""Governance API: submit, approvals inbox, delegation and workflow definitions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from eil.core.db import AsyncSession, get_db
from eil.core.errors import AppError
from eil.modules.execution.models import WorkItem
from eil.modules.execution.schemas import WorkItemRead
from eil.modules.execution.service import get_work_item
from eil.modules.governance.models import Approval
from eil.modules.governance.schemas import (
    ApprovalPage,
    ApprovalRead,
    DecideApprovalRequest,
    DelegateApprovalRequest,
    WorkflowDefRead,
    WorkflowInstanceRead,
)
from eil.modules.governance.service import (
    decide_approval,
    delegate_approval,
    escalate_overdue_approvals,
    list_approvals,
    list_workflow_definitions,
    list_workflow_instances,
    pending_approvals,
    submit_item,
)
from eil.modules.identity.rbac import (
    PermissionContext,
    require_any_permission,
    require_permission,
)
from eil.modules.seed_data import DEMAND_CREATE, RBAC_ADMIN, WORK_EDIT, WORK_VIEW

router = APIRouter(tags=["governance"])


async def _get_approval_for_ctx(
    session: AsyncSession, approval_id: UUID, ctx: PermissionContext
) -> tuple[Approval, WorkItem]:
    result = await session.execute(
        select(Approval, WorkItem)
        .join(WorkItem, WorkItem.id == Approval.work_item_id)
        .where(Approval.id == approval_id)
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(404, "not_found", "Not found", "Approval not found.")
    approval, item = row
    if ctx.scope == "own_org" and item.org_unit_id != ctx.user.org_unit_id:
        raise AppError(404, "not_found", "Not found", "Approval not found.")
    return approval, item


@router.post("/items/{item_id}/submit", response_model=WorkItemRead, status_code=202)
async def submit(
    item_id: UUID,
    ctx: Annotated[PermissionContext, Depends(require_any_permission(WORK_EDIT, DEMAND_CREATE))],
    session: Annotated[AsyncSession, Depends(get_db)],
    workflow_key: Annotated[str | None, Query()] = None,
) -> WorkItem:
    item = await get_work_item(session, item_id, ctx)
    return await submit_item(session, ctx, item, workflow_key)


@router.get("/approvals", response_model=ApprovalPage)
async def approvals(
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    scope: Annotated[str | None, Query(pattern="^(mine|all)$")] = None,
) -> ApprovalPage:
    selected = status or "pending"
    effective_scope = scope or "all"
    rows = await list_approvals(session, ctx, status=selected, limit=limit, scope=effective_scope)
    return ApprovalPage(items=list(rows), total=len(rows))


@router.get("/approvals/inbox", response_model=ApprovalPage)
async def approvals_inbox(
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> ApprovalPage:
    rows = await pending_approvals(session, ctx, limit=limit)
    return ApprovalPage(items=list(rows), total=len(rows))


@router.post("/approvals/escalate-overdue")
async def approve_escalation(
    ctx: Annotated[PermissionContext, Depends(require_permission(RBAC_ADMIN))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    return {"escalated": await escalate_overdue_approvals(session)}


@router.get("/approvals/{approval_id}", response_model=ApprovalRead)
async def approval_get(
    approval_id: UUID,
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Approval:
    approval, _ = await _get_approval_for_ctx(session, approval_id, ctx)
    return approval


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalRead)
async def approval_decide(
    approval_id: UUID,
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    payload: DecideApprovalRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Approval:
    return await decide_approval(session, ctx, approval_id, payload.decision, payload.comment)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
async def approval_approve(
    approval_id: UUID,
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
    payload: DecideApprovalRequest | None = None,
) -> Approval:
    decision = payload.decision if payload else "approved"
    return await decide_approval(
        session,
        ctx,
        approval_id,
        decision,
        payload.comment if payload else None,
    )


@router.post("/approvals/{approval_id}/delegate", response_model=ApprovalRead)
async def approval_delegate(
    approval_id: UUID,
    payload: DelegateApprovalRequest,
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Approval:
    await _get_approval_for_ctx(session, approval_id, ctx)
    return await delegate_approval(session, ctx, approval_id, payload.delegate_to)


@router.get("/workflows", response_model=list[WorkflowDefRead])
async def workflows(
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Sequence[Any]:
    return await list_workflow_definitions(session)


@router.get("/workflow-instances", response_model=list[WorkflowInstanceRead])
async def workflow_instances(
    ctx: Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
    work_item_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> Sequence[Any]:
    return await list_workflow_instances(session, ctx, work_item_id=work_item_id, limit=limit)
