"""Dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from eil.core.db import AsyncSession, get_db
from eil.modules.execution.schemas import WorkItemRead
from eil.modules.governance.dashboard import dashboard_summary
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import DASHBOARD_VIEW

router = APIRouter(tags=["governance"])


class DashboardSummary(BaseModel):
    as_of: datetime
    total: int
    statuses: dict[str, int]
    by_type: dict[str, int]
    rag: dict[str, int]
    overdue: int
    upcoming_milestones: list[WorkItemRead]
    pending_approvals: int
    pending_demands: list[WorkItemRead]
    recent_items: list[WorkItemRead]


@router.get("/dashboard", response_model=DashboardSummary)
async def dashboard(
    ctx: Annotated[PermissionContext, Depends(require_permission(DASHBOARD_VIEW))],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardSummary:
    summary = await dashboard_summary(session, ctx)
    return DashboardSummary(**summary)
