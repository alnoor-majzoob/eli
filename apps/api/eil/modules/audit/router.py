"""Audit API."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from eil.core.db import AsyncSession, get_db
from eil.core.errors import AppError
from eil.modules.audit.schemas import AuditRead, ChainVerificationResponse
from eil.modules.audit.service import (
    export_audit_csv,
    query_audit,
    serialize_audit,
    verify_chain,
)
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import AUDIT_VIEW

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditRead])
async def audit_list(
    ctx: Annotated[PermissionContext, Depends(require_permission(AUDIT_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
    actor_id: Annotated[str | None, Query()] = None,
    actor_type: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    from_ts: Annotated[datetime | None, Query()] = None,
    to_ts: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[dict[str, Any]]:
    if ctx.scope == "own_org" and actor_id not in (None, ctx.principal.subject):
        raise AppError(403, "forbidden", "Forbidden", "You can only view your own audit entries.")
    scope_org = ctx.user.org_unit_id if ctx.scope == "own_org" else None
    rows = await query_audit(
        session,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        org_unit_id=scope_org,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return [serialize_audit(row) for row in rows]


@router.get("/audit/verify", response_model=ChainVerificationResponse)
async def audit_verify(
    ctx: Annotated[PermissionContext, Depends(require_permission(AUDIT_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    result = await verify_chain(session)
    return {"rows": result.rows, "broken_at": result.broken_at, "ok": result.ok}


@router.get("/audit/export.csv")
async def audit_export(
    ctx: Annotated[PermissionContext, Depends(require_permission(AUDIT_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    scope_org = ctx.user.org_unit_id if ctx.scope == "own_org" else None
    rows = await export_audit_csv(session, org_unit_id=scope_org)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "seq",
            "ts",
            "actor_id",
            "actor_type",
            "action",
            "entity_type",
            "entity_id",
            "org_unit_id",
            "request_id",
            "reason",
            "hash",
        ],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)

    async def iterator() -> AsyncIterator[str]:
        yield buffer.getvalue()

    return StreamingResponse(
        iterator(), media_type="text/csv", headers={"Cache-Control": "no-store"}
    )
