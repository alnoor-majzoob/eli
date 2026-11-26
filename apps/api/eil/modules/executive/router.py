"""Executive view API (plan Phase 8, T8.4): `GET /executive/brief`.

Serves the auto-generated executive brief (fact sheet + numbers-guarded
LLM narration + template fallback) produced by
`eil.modules.assistant.brief.executive_brief`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.modules.assistant import brief
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import WORK_VIEW

router = APIRouter(tags=["executive"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/executive/brief")
async def executive_brief(ctx: CtxRead, session: Db) -> dict:
    return await brief.executive_brief(session, ctx)
