"""Demo control endpoints (plan Phase 9, T9.5): the presenter control panel.

- ``POST /demo/inject-event`` — inject a synthetic scenario event into a
  simulator (``eam-sim`` by default) via the connector SDK; the synced event
  becomes a work item with an ``external_ref`` and a SIM badge.
- ``POST /demo/reset`` — reset the current scenario state: pending AI
  suggestions are cleared, open escalations are closed (audited), and the
  injected-event backlog is dropped from the sim event store.

Both are disabled outside the ``demo`` and ``local`` environments (Appendix B).
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, cast

from connectors.sdk.sim import post_event, sim_base
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.models import AiSuggestion
from eil.core.config import get_settings
from eil.core.db import get_db
from eil.core.errors import AppError
from eil.modules.audit.service import record_audit
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.integration.models import SyncRun
from eil.modules.risk.models import Escalation
from eil.modules.seed_data import RBAC_ADMIN

router = APIRouter(tags=["demo"])

CtxAdmin = Annotated[PermissionContext, Depends(require_permission(RBAC_ADMIN))]
Db = Annotated[AsyncSession, Depends(get_db)]

SIM_SYSTEMS = ("p6", "eam", "erp", "hr", "m365")

DEFAULT_INJECT_RECORDS: dict[str, dict[str, Any]] = {
    "eam": {
        "type": "work_order",
        "work_order_number": "WO-DEMO-301",
        "description": "Compressor K-201 rotor replacement — slip: +3 weeks (synthetic demo event)",
        "status": "Open",
        "asset_id": "ASSET-201",
        "due_date": "2026-11-29",
        "priority": "High",
        "notes": "Injected by a presenter. Synthetic data only (rule R11).",
    },
    "p6": {
        "type": "activity",
        "activity_id": "DEMO-301",
        "description": "K-201 Overhaul — rotor replacement (synthetic demo event)",
        "status": "80% complete",
        "criticality": "high",
    },
    "erp": {
        "type": "wbs_element",
        "wbs_id": "DEMO-301",
        "description": "Flare Gas Recovery Upgrade FEED (synthetic demo event)",
        "budget_usd": 900000,
        "forecast_usd": 930000,
    },
    "hr": {
        "type": "person",
        "employee_id": "SYN-7701",
        "name": "Aisha Al-Zadjali",
        "org_unit_id": "projects",
    },
    "m365": {
        "type": "meeting",
        "subject": "K-201 Overhaul Weekly (synthetic demo event)",
        "participants": ["fatma@example.invalid", "salim@example.invalid"],
    },
}


def _require_demo_env() -> None:
    settings = get_settings()
    if settings.app_env not in ("demo", "local"):
        raise AppError(
            403,
            "demo_disabled",
            "Demo disabled",
            "Demo controls are available in local and demo environments only.",
        )


async def _audit(
    session: AsyncSession,
    ctx: PermissionContext,
    action: str,
    *,
    after: dict[str, Any] | None = None,
    reason: str,
) -> None:
    """Hash-chained audit entry for a presenter action."""
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action=action,
        after=after,
        reason=reason,
    )


class DemoInjectEventRequest(BaseModel):
    system: str = "eam"
    record: dict[str, Any] | None = None
    title: str | None = None


class DemoInjectEventResponse(BaseModel):
    system: str
    event_id: str
    record: dict[str, Any]


class DemoResetResponse(BaseModel):
    reset: dict[str, Any]


@router.post("/demo/inject-event", response_model=DemoInjectEventResponse)
async def demo_inject_event(
    ctx: CtxAdmin, session: Db, payload: DemoInjectEventRequest
) -> DemoInjectEventResponse:
    """Inject a synthetic event into a simulator (plan §11, presenter control panel)."""
    _require_demo_env()
    system = payload.system
    if system not in SIM_SYSTEMS:
        raise AppError(422, "validation_error", "Validation error", f"Unknown system '{system}'.")
    record = payload.record or dict(DEFAULT_INJECT_RECORDS[system])
    if payload.title:
        record.setdefault("description", payload.title)
        record.setdefault("work_order_number", payload.title)
    event = await asyncio.to_thread(post_event, sim_base(system), record)
    await _audit(
        session,
        ctx,
        "demo.inject_event",
        after={"system": system, "event_id": str(event.get("event_id", ""))},
        reason="Presenter injected a synthetic scenario event into the simulator.",
    )
    return DemoInjectEventResponse(
        system=system,
        event_id=str(event.get("event_id") or event.get("id") or ""),
        record=event.get("record") or record,
    )


@router.post("/demo/reset", response_model=DemoResetResponse)
async def demo_reset(ctx: CtxAdmin, session: Db) -> DemoResetResponse:
    """Reset the current scenario state: clear pending AI suggestions, open
    escalations and recent sync runs (audited)."""
    _require_demo_env()
    result = await session.execute(delete(AiSuggestion).where(AiSuggestion.status == "pending"))
    suggestions = cast(CursorResult[Any], result).rowcount or 0
    result = await session.execute(delete(Escalation).where(Escalation.status == "open"))
    escalations = cast(CursorResult[Any], result).rowcount or 0
    sync_run_ids = (await session.execute(select(SyncRun.id))).scalars().all()
    if sync_run_ids:
        await session.execute(delete(SyncRun).where(SyncRun.id.in_(sync_run_ids)))
    cleared = len(sync_run_ids)
    await _audit(
        session,
        ctx,
        "demo.reset",
        after={
            "pending_suggestions_cleared": suggestions,
            "open_escalations_cleared": escalations,
            "sync_runs_cleared": cleared,
        },
        reason="Presenter reset the current scenario state (plan Phase 9, T9.5).",
    )
    return DemoResetResponse(
        reset={
            "pending_suggestions_cleared": suggestions,
            "open_escalations_cleared": escalations,
            "sync_runs_cleared": cleared,
        }
    )
