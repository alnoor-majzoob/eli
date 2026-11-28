"""Workflow and approval service.

Phase 1 implements a data-driven workflow runner: definitions are JSON documents
(states + transitions + an approval chain with roles, permissions and SLAs), and
instances record each sequential approval step. Segregation-of-duties rules are
enforced for every decision and every denial is audited.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.audit.service import record_audit
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.execution.service import _audit_view
from eil.modules.governance.models import Approval, WorkflowDefinition, WorkflowInstance
from eil.modules.identity.rbac import (
    PermissionContext,
    resolve_permission_scope,
)
from eil.modules.prioritization.conversion import convert_demand_to_delivery
from eil.modules.seed_data import (
    DEMAND_APPROVE,
    DEPT_HEAD_APPROVE,
    PRIORITY_OVERRIDE,
    SCENARIO_PROMOTE,
    workflow_key_for,
)

logger = structlog.get_logger(__name__)

DECISION = Literal["approved", "rejected"]

_ROLE_APPROVAL_PERMISSIONS = {
    "executive": DEMAND_APPROVE,
    "portfolio_manager": DEMAND_APPROVE,
    "dept_head": DEPT_HEAD_APPROVE,
}
_EXTRA_ROLE_PERMISSIONS = {
    "priority_override": {"portfolio_manager": PRIORITY_OVERRIDE},
    "scenario_promotion": {"portfolio_manager": SCENARIO_PROMOTE},
}


async def get_workflow_definition(session: AsyncSession, key: str) -> WorkflowDefinition:
    result = await session.execute(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.key == key, WorkflowDefinition.active)
        .order_by(WorkflowDefinition.version.desc())
        .limit(1)
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise AppError(404, "not_found", "Not found", f"Workflow definition '{key}' not found.")
    return definition


async def list_workflow_definitions(session: AsyncSession) -> Sequence[WorkflowDefinition]:
    result = await session.execute(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.active)
        .order_by(WorkflowDefinition.name)
    )
    return list(result.scalars().all())


def _approval_permission(workflow_key: str, approver_role: str) -> str:
    return _EXTRA_ROLE_PERMISSIONS.get(workflow_key, {}).get(
        approver_role, _ROLE_APPROVAL_PERMISSIONS.get(approver_role, DEMAND_APPROVE)
    )


def _submit_config(definition: WorkflowDefinition) -> dict[str, Any]:
    transitions = definition.definition.get("transitions", {})
    config = transitions.get("submit")
    if not isinstance(config, dict):
        raise AppError(500, "workflow_invalid", "Workflow error", "Submit transition is missing.")
    return config


def _approval_chain(definition: WorkflowDefinition) -> list[dict[str, Any]]:
    chain = _submit_config(definition).get("approval_chain")
    if not isinstance(chain, list) or not chain:
        raise AppError(500, "workflow_invalid", "Workflow error", "Approval chain is missing.")
    return [step for step in chain if isinstance(step, dict)]


async def _authorize_approver(
    session: AsyncSession,
    ctx: PermissionContext,
    approval: Approval,
    item: WorkItem,
    workflow_key: str,
) -> None:
    if ctx.is_admin:
        return
    if approval.delegated_to is not None:
        if approval.delegated_to != ctx.user.id:
            raise AppError(
                403,
                "forbidden",
                "Forbidden",
                "This approval has been delegated to another user.",
            )
    elif approval.approver_role not in ctx.roles:
        raise AppError(
            403,
            "forbidden",
            "Forbidden",
            f"Approval step requires the '{approval.approver_role}' role.",
            extra={"required_role": approval.approver_role},
        )

    permission = _approval_permission(workflow_key, approval.approver_role)
    scope = await resolve_permission_scope(session, [approval.approver_role], permission)
    if scope == "none":
        raise AppError(
            403,
            "forbidden",
            "Forbidden",
            f"Role '{approval.approver_role}' lacks '{permission}'.",
            extra={"permission": permission},
        )
    if scope == "own_org" and item.org_unit_id != ctx.user.org_unit_id:
        raise AppError(
            404,
            "not_found",
            "Not found",
            "Approval not found or not visible.",
        )


async def _record_denial(
    session: AsyncSession,
    ctx: PermissionContext,
    approval: Approval,
    item: WorkItem,
    reason: str,
    code: str,
    rule: str | None = None,
) -> None:
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="approval.denied",
        entity_type="work_item",
        entity_id=item.id,
        org_unit_id=item.org_unit_id,
        after=_audit_view(item),
        reason=reason,
    )
    await session.commit()
    if rule:
        raise AppError(
            403,
            code,
            "Segregation of duties violation",
            reason,
            extra={"rule": rule, "approval_id": str(approval.id)},
        )
    raise AppError(403, code, "Forbidden", reason, extra={"approval_id": str(approval.id)})


async def submit_item(
    session: AsyncSession,
    ctx: PermissionContext,
    item: WorkItem,
    workflow_key: str | None = None,
) -> WorkItem:
    key = workflow_key_for(item.type, workflow_key)
    definition = await get_workflow_definition(session, key)
    submit_cfg = _submit_config(definition)
    allowed_from = set(submit_cfg.get("from", []))
    if item.status not in allowed_from:
        raise AppError(
            409,
            "conflict",
            "Conflict",
            f"Cannot submit a {item.status} item through '{definition.name}'.",
            extra={"allowed_from": sorted(allowed_from)},
        )

    chain = _approval_chain(definition)
    before = _audit_view(item)

    running = (
        await session.execute(
            select(WorkflowInstance)
            .where(
                WorkflowInstance.work_item_id == item.id,
                WorkflowInstance.status == "running",
            )
            .order_by(WorkflowInstance.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if running is None:
        instance = WorkflowInstance(
            definition_id=definition.id,
            work_item_id=item.id,
            step=1,
            current_state="submitted",
            status="running",
            requested_by=ctx.user.id,
        )
        session.add(instance)
        await session.flush()
    else:
        instance = running
        instance.current_state = "submitted"

    existing_pending = (
        await session.execute(
            select(Approval).where(
                Approval.instance_id == instance.id, Approval.status == "pending"
            )
        )
    ).scalar_one_or_none()
    if existing_pending is None:
        first = chain[0]
        sla_hours = int(first.get("sla_hours", 48))
        approval = Approval(
            instance_id=instance.id,
            work_item_id=item.id,
            step=1,
            approver_role=str(first.get("role", "portfolio_manager")),
            status="pending",
            requested_by=ctx.user.id,
            due_at=utcnow() + timedelta(hours=sla_hours),
        )
        session.add(approval)

    item.status = "submitted"
    item.updated_at = utcnow()
    item.version += 1
    await session.commit()
    await session.refresh(item)

    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_item.submitted",
        entity_type="work_item",
        entity_id=item.id,
        org_unit_id=item.org_unit_id,
        before={"status": before["status"], "version": before["version"]},
        after=_audit_view(item),
        reason=f"Submitted through workflow '{definition.name}'.",
    )
    await session.commit()
    return item


async def decide_approval(
    session: AsyncSession,
    ctx: PermissionContext,
    approval_id: UUID,
    decision: DECISION,
    comment: str | None = None,
) -> Approval:
    if decision not in ("approved", "rejected"):
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            "Decision must be approved or rejected.",
        )

    row = (
        await session.execute(
            select(Approval, WorkItem)
            .join(WorkItem, WorkItem.id == Approval.work_item_id)
            .where(Approval.id == approval_id, Approval.status == "pending")
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "not_found", "Not found", "Pending approval not found.")
    approval, item = row

    instance = (
        await session.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == approval.instance_id)
        )
    ).scalar_one()
    definition = (
        await session.execute(
            select(WorkflowDefinition).where(WorkflowDefinition.id == instance.definition_id)
        )
    ).scalar_one()

    try:
        await _authorize_approver(session, ctx, approval, item, definition.key)
    except AppError as exc:
        await _record_denial(session, ctx, approval, item, exc.detail, "forbidden")
        raise

    if approval.requested_by == ctx.user.id or item.created_by == ctx.user.id:
        await _record_denial(
            session,
            ctx,
            approval,
            item,
            "A user cannot approve a demand, stage gate or change request "
            "they created or submitted.",
            "sod_violation",
            "SOD-1",
        )

    if approval.escalated_at is not None:
        logger.info(
            "approval_decided_after_escalation",
            approval_id=str(approval.id),
            escalated_at=approval.escalated_at.isoformat(),
        )

    before = _audit_view(item)
    approval.status = decision
    approval.decided_by = ctx.user.id
    approval.decided_at = utcnow()
    approval.comment = comment
    approval.decision_reason = comment

    if decision == "rejected":
        instance.status = "cancelled"
        instance.current_state = "rejected"
        instance.completed_at = utcnow()
        item.status = "rejected"
    else:
        chain = _approval_chain(definition)
        next_step = approval.step + 1
        if next_step <= len(chain):
            step_cfg = chain[next_step - 1]
            sla_hours = int(step_cfg.get("sla_hours", 48))
            session.add(
                Approval(
                    instance_id=instance.id,
                    work_item_id=item.id,
                    step=next_step,
                    approver_role=str(step_cfg.get("role", "portfolio_manager")),
                    status="pending",
                    requested_by=approval.requested_by,
                    due_at=utcnow() + timedelta(hours=sla_hours),
                )
            )
            instance.step = next_step
            instance.current_state = f"submitted_step_{next_step}"
        else:
            instance.status = "completed"
            instance.current_state = "approved"
            instance.completed_at = utcnow()
            item.status = "approved"
            # T5.4 (plan §10, Phase 5): approved demands convert to delivery projects.
            if item.type == WorkType.DEMAND:
                await convert_demand_to_delivery(session, ctx, item.id)

    item.updated_at = utcnow()
    item.version += 1
    await session.commit()
    await session.refresh(item)

    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_item.approved" if decision == "approved" else "work_item.rejected",
        entity_type="work_item",
        entity_id=item.id,
        org_unit_id=item.org_unit_id,
        before=before,
        after=_audit_view(item),
        reason=comment or f"Workflow '{definition.name}' decision: {decision}.",
    )
    await session.commit()
    return approval


async def delegate_approval(
    session: AsyncSession,
    ctx: PermissionContext,
    approval_id: UUID,
    delegate_to: UUID,
) -> Approval:
    approval = (
        await session.execute(
            select(Approval).where(Approval.id == approval_id, Approval.status == "pending")
        )
    ).scalar_one_or_none()
    if approval is None:
        raise AppError(404, "not_found", "Not found", "Pending approval not found.")
    if not ctx.is_admin and approval.approver_role not in ctx.roles:
        raise AppError(403, "forbidden", "Forbidden", "Only the assigned approver can delegate.")
    if delegate_to == ctx.user.id:
        raise AppError(422, "validation_error", "Validation error", "Cannot delegate to yourself.")

    approval.delegated_to = delegate_to
    approval.delegated_by = ctx.user.id
    approval.delegated_at = utcnow()
    await session.commit()
    await session.refresh(approval)
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="approval.delegated",
        entity_type="approval",
        entity_id=approval.id,
        after={"delegated_to": str(delegate_to)},
        reason="Approval delegated.",
    )
    await session.commit()
    return approval


async def pending_approvals(
    session: AsyncSession, ctx: PermissionContext, limit: int = 100
) -> Sequence[Approval]:
    stmt = (
        select(Approval, WorkItem)
        .join(WorkItem, WorkItem.id == Approval.work_item_id)
        .where(Approval.status == "pending")
    )
    if ctx.scope == "own_org":
        stmt = stmt.where(WorkItem.org_unit_id == ctx.user.org_unit_id)
    if not ctx.is_admin:
        stmt = stmt.where(
            (Approval.approver_role.in_(ctx.roles)) | (Approval.delegated_to == ctx.user.id)
        )
    stmt = stmt.order_by(Approval.due_at, Approval.created_at, Approval.id).limit(limit)
    rows = (await session.execute(stmt)).all()
    return [row[0] for row in rows]


async def list_approvals(
    session: AsyncSession,
    ctx: PermissionContext,
    status: str = "pending",
    limit: int = 100,
    scope: str = "all",
) -> Sequence[Approval]:
    stmt = (
        select(Approval)
        .join(WorkItem, WorkItem.id == Approval.work_item_id)
        .where(Approval.status == status)
    )
    if ctx.scope == "own_org":
        stmt = stmt.where(WorkItem.org_unit_id == ctx.user.org_unit_id)
    # "mine" restricts to approvals the caller can act on; "all" returns every
    # approval in the caller's (org) scope.
    if scope == "mine":
        stmt = stmt.where(
            (Approval.approver_role.in_(ctx.roles)) | (Approval.delegated_to == ctx.user.id)
        )
    stmt = stmt.order_by(Approval.created_at.desc(), Approval.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def list_workflow_instances(
    session: AsyncSession,
    ctx: PermissionContext,
    work_item_id: UUID | None = None,
    limit: int = 100,
) -> Sequence[WorkflowInstance]:
    stmt = select(WorkflowInstance).join(WorkItem, WorkItem.id == WorkflowInstance.work_item_id)
    if work_item_id is not None:
        stmt = stmt.where(WorkflowInstance.work_item_id == work_item_id)
    if ctx.scope == "own_org":
        stmt = stmt.where(WorkItem.org_unit_id == ctx.user.org_unit_id)
    stmt = stmt.order_by(WorkflowInstance.updated_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def escalate_overdue_approvals(
    session: AsyncSession, now: datetime | None = None, limit: int = 500
) -> int:
    """Mark pending approvals whose SLA elapsed and audit the escalation."""
    moment = now or utcnow()
    rows = list(
        (
            await session.execute(
                select(Approval)
                .where(
                    Approval.status == "pending",
                    Approval.due_at.is_not(None),
                    Approval.due_at < moment,
                    Approval.escalated_at.is_(None),
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for approval in rows:
        approval.escalated_at = moment
        await record_audit(
            session,
            actor_id="system",
            actor_type="system",
            action="approval.escalated",
            entity_type="approval",
            entity_id=approval.id,
            reason=f"Approval SLA elapsed at {moment.isoformat()}.",
        )
        logger.warning("approval_escalated", approval_id=str(approval.id))
    if rows:
        await session.commit()
    return len(rows)
