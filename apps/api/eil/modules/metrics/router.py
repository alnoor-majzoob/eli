"""Executive metrics API (plan Phase 8, T8.1): `GET /metrics/summary`."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.core.errors import AppError
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.metrics import service
from eil.modules.seed_data import DASHBOARD_VIEW

router = APIRouter(tags=["metrics"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(DASHBOARD_VIEW))]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/metrics/summary")
async def metrics_summary(
    ctx: CtxRead,
    session: Db,
    as_of: Annotated[
        str | None,
        Query(
            description="Replay the executive view as of this ISO datetime (T8.5 presenter mode).",
        ),
    ] = None,
) -> dict:
    parsed: datetime | None = None
    if as_of is not None:
        try:
            parsed = datetime.fromisoformat(as_of)
        except ValueError:
            raise AppError(
                422, "validation_error", "Validation error", "Invalid ISO datetime for 'as_of'."
            ) from None
    return await service.executive_summary(session, ctx, as_of=parsed)
