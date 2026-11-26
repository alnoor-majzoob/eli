"""Write-back framework (plan §10, Phase 3, T3.5/T3.7).

Default-off enforcement: nothing happens unless the approved source has
``write_back_enabled`` and the action is on the ``write_back_fields`` allow-list.
Approval-gated by default; executing the change calls ``connector.push`` and is
audited.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from connectors.sdk.registry import get_connector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.audit.service import record_audit
from eil.modules.integration.models import ApprovedSource, WriteBackChange
from eil.modules.integration.schemas import WriteBackChangeRead


async def _load_source(session: AsyncSession, source_id: UUID) -> ApprovedSource:
    source = (
        await session.execute(select(ApprovedSource).where(ApprovedSource.id == source_id))
    ).scalar_one_or_none()
    if source is None:
        raise AppError(404, "not_found", "Not found", "Approved source not found.")
    return source


async def submit_writeback(
    session: AsyncSession,
    source: ApprovedSource,
    work_item_id: UUID,
    action: str,
    payload: dict[str, Any],
) -> WriteBackChange | None:
    """Enqueue a gated write-back change; ``None`` when the policy disallows it."""
    if not source.write_back_enabled:
        return None
    if source.write_back_fields and action not in source.write_back_fields:
        return None
    change = WriteBackChange(
        source_id=source.id,
        work_item_id=work_item_id,
        action=action,
        payload=payload,
        status="pending",
    )
    session.add(change)
    await session.commit()
    await session.refresh(change)
    return change


async def approve_writeback(session: AsyncSession, ctx: Any, change_id: UUID) -> WriteBackChange:
    change = (
        await session.execute(select(WriteBackChange).where(WriteBackChange.id == change_id))
    ).scalar_one_or_none()
    if change is None:
        raise AppError(404, "not_found", "Not found", "Write-back change not found.")
    if change.status != "pending":
        raise AppError(409, "conflict", "Conflict", "Write-back change is not pending.")
    change.status = "approved"
    change.approved_by = ctx.user.id
    session.add(change)
    await session.commit()
    await session.refresh(change)
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="write_back.approved",
        entity_type="write_back_change",
        entity_id=change.id,
        reason="Write-back approved.",
    )
    await session.commit()
    return change


async def execute_writeback(session: AsyncSession, change_id: UUID) -> WriteBackChange:
    change = (
        await session.execute(select(WriteBackChange).where(WriteBackChange.id == change_id))
    ).scalar_one_or_none()
    if change is None:
        raise AppError(404, "not_found", "Not found", "Write-back change not found.")
    if change.status != "approved":
        raise AppError(409, "conflict", "Conflict", "Write-back change is not approved.")
    source = await _load_source(session, change.source_id)
    connector = get_connector(source.type)
    connector.push({"action": change.action, **change.payload})
    change.status = "executed"
    change.executed_at = utcnow()
    session.add(change)
    await session.commit()
    await record_audit(
        session,
        actor_id=None,
        actor_type="system",
        action="write_back.executed",
        entity_type="write_back_change",
        entity_id=change.id,
        reason=f"Connector {source.type} push executed ({change.action}).",
    )
    await session.commit()
    return change


def write_back_read(change: WriteBackChange) -> WriteBackChangeRead:
    return WriteBackChangeRead.model_validate(change)
