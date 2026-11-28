"""Integration admin API (plan §10, Phase 3, T3.5/T3.6/T3.7).

- Connector registry (read-only): what systems are available, modes, push support.
- Approved Source Registry (T3.5): CRUD + SoD-4 two-person rule on protected changes.
- Sync orchestration (T3.6): "Sync now", status (health + lag), conflicts, write-backs.
- Webhook receivers: sims push records here (T3.3/T3.6).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from connectors.sdk.registry import BUILTIN_CONNECTORS, get_connector, mode_for
from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.audit.service import record_audit
from eil.modules.execution.service import get_work_item
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.integration.models import (
    ApprovedSource,
    SyncConflict,
    WriteBackChange,
)
from eil.modules.integration.schemas import (
    ApprovedSourceCreate,
    ApprovedSourceRead,
    ApprovedSourceStatusRead,
    ApprovedSourceUpdate,
    ConnectorCapabilityRead,
    ConnectorRead,
    SyncConflictRead,
    SyncRunRead,
    WebhookRead,
    WriteBackChangeRead,
    WriteBackChangeSubmit,
)
from eil.modules.integration.sync import source_health, sync_from_webhook, sync_source
from eil.modules.integration.writeback import (
    approve_writeback,
    execute_writeback,
    submit_writeback,
)
from eil.modules.seed_data import CONNECTOR_MANAGE, WORK_EDIT

router = APIRouter(tags=["integration"])

CtxAdmin = Annotated[PermissionContext, Depends(require_permission(CONNECTOR_MANAGE))]
CtxEdit = Annotated[PermissionContext, Depends(require_permission(WORK_EDIT))]
Db = Annotated[AsyncSession, Depends(get_db)]

# SoD-4 (plan §13.2): "Changes to the Approved Source Registry or AI-processing
# flags require two distinct people (requester != approver)."
_PROTECTED_FIELDS = frozenset(
    {
        "type",
        "ai_processing_allowed",
        "owned_fields",
        "write_back_enabled",
        "write_back_fields",
        "write_back_requires_approval",
    }
)


async def _get_source(session: AsyncSession, source_id: UUID) -> ApprovedSource:
    source = (
        await session.execute(select(ApprovedSource).where(ApprovedSource.id == source_id))
    ).scalar_one_or_none()
    if source is None:
        raise AppError(404, "not_found", "Not found", "Approved source not found.")
    return source


async def _assert_change_allowed(
    ctx: PermissionContext, data: dict[str, Any], session: AsyncSession
) -> None:
    changed = set(data) & _PROTECTED_FIELDS
    if not changed:
        return
    approved_by = data.get("approved_by")
    if not approved_by or approved_by == ctx.principal.subject:
        raise AppError(
            403,
            "sod_violation",
            "SOD-4: two-person rule",
            "Changes to the approved source registry or AI-processing flags require "
            "two distinct people (requester != approver).",
            extra={"changed_fields": sorted(changed)},
        )


@router.get("/integrations/connectors", response_model=list[ConnectorRead])
async def connectors_list(ctx: CtxAdmin) -> list[ConnectorRead]:
    result = []
    for system in sorted(BUILTIN_CONNECTORS):
        connector = get_connector(system)
        caps = connector.capabilities()
        result.append(
            ConnectorRead(
                system=caps.system,
                capabilities=ConnectorCapabilityRead(
                    system=caps.system,
                    record_types=list(caps.record_types),
                    modes=list(caps.modes),
                    default_mode=caps.default_mode,
                    push_supported=caps.push_supported,
                ),
                mode=mode_for(system),
                push_supported=caps.push_supported,
            )
        )
    return result


@router.get("/integrations/sources", response_model=list[ApprovedSourceRead])
async def sources_list(ctx: CtxAdmin, session: Db) -> list[ApprovedSourceRead]:
    sources = (
        (
            await session.execute(
                select(ApprovedSource).order_by(ApprovedSource.name, ApprovedSource.id)
            )
        )
        .scalars()
        .all()
    )
    return [ApprovedSourceRead.model_validate(source) for source in sources]


@router.post("/integrations/sources", response_model=ApprovedSourceRead, status_code=201)
async def source_create(
    ctx: CtxAdmin, session: Db, payload: ApprovedSourceCreate
) -> ApprovedSourceRead:
    if payload.type not in BUILTIN_CONNECTORS:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            f"Unknown connector system '{payload.type}'.",
        )
    data = payload.model_dump()
    data["created_by"] = ctx.user.id
    source = ApprovedSource(**data)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="approved_source.created",
        entity_type="approved_source",
        entity_id=source.id,
        reason=f"Approved source created: {payload.type}/{payload.name}.",
    )
    await session.commit()
    return ApprovedSourceRead.model_validate(source)


@router.patch("/integrations/sources/{source_id}", response_model=ApprovedSourceRead)
async def source_update(
    source_id: UUID, ctx: CtxAdmin, session: Db, payload: ApprovedSourceUpdate
) -> ApprovedSourceRead:
    source = await _get_source(session, source_id)
    data = payload.model_dump(exclude_unset=True)
    await _assert_change_allowed(ctx, data, session)
    data.pop("approved_by", None)
    data.pop("reason", None)

    for key, value in data.items():
        setattr(source, key, value)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="approved_source.updated",
        entity_type="approved_source",
        entity_id=source.id,
        reason=payload.reason or f"Approved source updated: {source.name}.",
    )
    await session.commit()
    return ApprovedSourceRead.model_validate(source)


@router.delete("/integrations/sources/{source_id}", status_code=204)
async def source_delete(source_id: UUID, ctx: CtxAdmin, session: Db) -> None:
    source = await _get_source(session, source_id)
    if source.enabled:
        raise AppError(409, "conflict", "Conflict", "Disable the source before deleting it.")
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="approved_source.deleted",
        entity_type="approved_source",
        entity_id=source.id,
        reason=f"Approved source deleted: {source.name}.",
    )
    await session.delete(source)
    await session.commit()


@router.post("/integrations/sources/{source_id}/sync", response_model=SyncRunRead)
async def source_sync(source_id: UUID, ctx: CtxAdmin, session: Db) -> SyncRunRead:
    source = await _get_source(session, source_id)
    run = await sync_source(session, source, triggered_by="api")
    return SyncRunRead.model_validate(run)


@router.get("/integrations/sources/{source_id}/status", response_model=ApprovedSourceStatusRead)
async def source_status(source_id: UUID, ctx: CtxAdmin, session: Db) -> ApprovedSourceStatusRead:
    source = await _get_source(session, source_id)
    return await source_health(session, source)


@router.get("/integrations/sources/{source_id}/conflicts", response_model=list[SyncConflictRead])
async def source_conflicts(source_id: UUID, ctx: CtxAdmin, session: Db) -> list[SyncConflictRead]:
    source = await _get_source(session, source_id)
    rows = (
        (
            await session.execute(
                select(SyncConflict)
                .where(SyncConflict.source_id == source.id)
                .order_by(SyncConflict.created_at.desc(), SyncConflict.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [SyncConflictRead.model_validate(row) for row in rows]


@router.post(
    "/integrations/sources/{source_id}/conflicts/{conflict_id}/resolve",
    response_model=SyncConflictRead,
)
async def source_conflict_resolve(
    source_id: UUID,
    conflict_id: UUID,
    ctx: CtxAdmin,
    session: Db,
    payload: Any | None = Body(default=None),
) -> SyncConflictRead:
    conflict = (
        await session.execute(
            select(SyncConflict).where(
                SyncConflict.id == conflict_id, SyncConflict.source_id == source_id
            )
        )
    ).scalar_one_or_none()
    if conflict is None:
        raise AppError(404, "not_found", "Not found", "Conflict not found.")
    conflict.resolved = True
    conflict.resolved_at = utcnow()
    session.add(conflict)
    await session.commit()
    return SyncConflictRead.model_validate(conflict)


@router.post(
    "/integrations/sources/{source_id}/writebacks",
    response_model=WriteBackChangeRead,
    status_code=201,
)
async def source_writeback_submit(
    source_id: UUID, ctx: CtxAdmin, session: Db, payload: WriteBackChangeSubmit
) -> WriteBackChangeRead:
    """Enqueue a gated write-back change (plan §10, Phase 3, T7)."""
    source = await _get_source(session, source_id)
    await get_work_item(session, payload.work_item_id, ctx)  # authorisation
    change = await submit_writeback(
        session, source, payload.work_item_id, payload.action, payload.payload
    )
    if change is None:
        raise AppError(
            409,
            "conflict",
            "Conflict",
            "Write-back disabled for this source or action.",
            extra={"source_id": str(source.id)},
        )
    return WriteBackChangeRead.model_validate(change)


@router.get(
    "/integrations/sources/{source_id}/writebacks", response_model=list[WriteBackChangeRead]
)
async def source_writebacks(
    source_id: UUID, ctx: CtxAdmin, session: Db
) -> list[WriteBackChangeRead]:
    source = await _get_source(session, source_id)
    rows = (
        (
            await session.execute(
                select(WriteBackChange)
                .where(
                    WriteBackChange.source_id == source.id,
                    WriteBackChange.status.in_(["pending", "approved"]),
                )
                .order_by(WriteBackChange.created_at.desc(), WriteBackChange.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [WriteBackChangeRead.model_validate(row) for row in rows]


@router.post(
    "/integrations/sources/{source_id}/writebacks/{change_id}/approve",
    response_model=WriteBackChangeRead,
)
async def source_writeback_approve(
    source_id: UUID, change_id: UUID, ctx: CtxAdmin, session: Db
) -> WriteBackChangeRead:
    change = await approve_writeback(session, ctx, change_id)
    return WriteBackChangeRead.model_validate(change)


@router.post("/integrations/sources/{source_id}/writebacks/{change_id}/execute", status_code=204)
async def source_writeback_execute(
    source_id: UUID, change_id: UUID, ctx: CtxAdmin, session: Db
) -> None:
    await execute_writeback(session, change_id)


@router.post("/integrations/webhooks/{system}/{record_id}", response_model=WebhookRead)
async def webhook_receive(
    system: str,
    record_id: str,
    ctx: CtxAdmin,
    session: Db,
    payload: Any = Body(default=None),
) -> WebhookRead:
    """Simulator webhook receiver: ingest pushed records (plan §10, T3.3).

    Requires connector.manage; only ingests into an *enabled* approved source.
    """
    if system not in BUILTIN_CONNECTORS:
        raise AppError(404, "not_found", "Not found", "Unknown connector system.")
    source = (
        (
            await session.execute(
                select(ApprovedSource)
                .where(ApprovedSource.type == system, ApprovedSource.enabled.is_(True))
                .order_by(ApprovedSource.name, ApprovedSource.id)
            )
        )
        .scalars()
        .first()
    )
    if source is None:
        raise AppError(404, "not_found", "Not found", "No enabled approved source for this system.")
    connector = get_connector(system)
    raws = connector.handle_webhook({"record_id": record_id, "payload": payload})
    accepted = await sync_from_webhook(session, source, raws)
    return WebhookRead(system=system, accepted=accepted)
