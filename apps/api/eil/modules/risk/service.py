"""Predictive execution service (plan §9.5, Phase 7, T7.4-T7.6).

- ``rollup_confidence`` — confidence roll-up heuristic (plan §9.5):
  ``conf_parent = 0.6 x min(critical children) + 0.4 x weighted_mean(children)``.
- ``recalc_confidence`` — event-driven recalculation core (T7.5).
- ``generate_escalations`` — escalation rules ESC-1..ESC-4 (plan §9.6, T7.6).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.models import utcnow
from eil.core.outbox import emit
from eil.modules.capacity import engine as capacity_engine
from eil.modules.capacity.models import Competency
from eil.modules.execution.models import WorkItem, WorkItemStatus, WorkType
from eil.modules.graph.service import downstream_impact
from eil.modules.identity.rbac import PermissionContext
from eil.modules.risk import engine
from eil.modules.risk.models import Escalation

PARENT_TYPES = (WorkType.COMMITMENT, WorkType.PROJECT, WorkType.INITIATIVE, WorkType.OBJECTIVE)


async def _emit_confidence_changed(session: AsyncSession, updated: dict[UUID, Decimal]) -> None:
    """Emit one ``confidence_changed`` domain event per updated item (T7.5)."""
    for item_id, confidence in updated.items():
        await emit(
            session,
            "confidence_changed",
            {
                "item_id": str(item_id),
                "confidence": float(confidence),
                "at": utcnow().isoformat(),
            },
        )


async def _children(session: AsyncSession, ctx: PermissionContext, item_id: UUID) -> list[WorkItem]:
    try:
        impact = await downstream_impact(session, ctx, item_id)
    except Exception:
        return []
    ids = [row.id for row in impact.items if row.type in PARENT_TYPES]
    if not ids:
        return []
    rows = (await session.execute(select(WorkItem).where(WorkItem.id.in_(ids)))).scalars().all()
    return list(rows)


async def rollup_confidence(session: AsyncSession, ctx: PermissionContext) -> dict[UUID, Decimal]:
    """Roll delivery confidence up to parents via the §9.5 heuristic."""
    written: dict[UUID, Decimal] = {}
    items = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type.in_(PARENT_TYPES),
                    WorkItem.delivery_confidence.is_(None),
                    WorkItem.status.notin_((WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)),
                )
            )
        )
        .scalars()
        .all()
    )
    for item in items:
        children = await _children(session, ctx, item.id)
        if not children:
            continue
        child_confidences = [
            child.delivery_confidence for child in children if child.delivery_confidence is not None
        ]
        critical = [c for c in child_confidences if c < Decimal("0.5")]
        weighted_mean = (
            sum(child_confidences, Decimal("0")) / Decimal(len(child_confidences))
            if child_confidences
            else Decimal("0")
        )
        if critical:
            item.delivery_confidence = (
                Decimal("0.6") * min(critical) + Decimal("0.4") * weighted_mean
            )
        else:
            item.delivery_confidence = weighted_mean
        written[item.id] = item.delivery_confidence
    await _emit_confidence_changed(session, written)
    await session.commit()
    return written


async def recalc_confidence(session: AsyncSession, item_ids: list[UUID]) -> dict[UUID, Decimal]:
    """Event-driven recalculation core (plan §9.5, T7.5).

    Re-runs the Monte Carlo on the schedule network and updates each affected
    item's ``delivery_confidence``; returns the new values.
    """
    if not item_ids:
        return {}
    network = await engine.build_schedule_network(session)
    result = engine.run_monte_carlo(network, iterations=5000, seed=42)
    items = {
        row.id: row
        for row in (await session.execute(select(WorkItem).where(WorkItem.id.in_(item_ids))))
        .scalars()
        .all()
    }
    horizon_start = min(
        (item.planned_start for item in items.values() if item.planned_start),
        default=date.today(),
    )
    updated: dict[UUID, Decimal] = {}
    for item_id in item_ids:
        item = items.get(item_id)
        if item is None:
            continue
        committed = item.baseline_end or item.planned_end
        if committed is None:
            continue
        committed_days = (committed - horizon_start).days + 1
        confidence = engine.delivery_confidence(result["finish"], item_id, committed_days)
        item.delivery_confidence = confidence
        updated[item_id] = confidence
    await _emit_confidence_changed(session, updated)
    await session.commit()
    return updated


def _new_escalation(
    work_item: WorkItem | None,
    *,
    root_cause: str,
    target_role: str,
    sla_days: int,
    recommended_actions: list[dict[str, Any]],
    required_decision: str | None,
    competency_id: UUID | None = None,
) -> Escalation:
    return Escalation(
        work_item_id=work_item.id if work_item is not None else None,
        competency_id=competency_id,
        root_cause=root_cause,
        recommended_actions=recommended_actions,
        required_decision=required_decision,
        target_role=target_role,
        sla_days=sla_days,
        due_at=utcnow() + timedelta(days=sla_days),
        status="open",
    )


async def _escalation_exists(
    session: AsyncSession, work_item_id: UUID | None, competency_id: UUID | None = None
) -> bool:
    filters = [Escalation.status == "open"]
    if work_item_id is not None:
        filters.append(Escalation.work_item_id == work_item_id)
    else:
        filters.append(Escalation.work_item_id.is_(None))
    if competency_id is not None:
        filters.append(Escalation.competency_id == competency_id)
    row = (await session.execute(select(Escalation).where(*filters))).scalars().first()
    return row is not None


async def _esc1_commitments(session: AsyncSession) -> list[Escalation]:
    items = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type == WorkType.COMMITMENT,
                    WorkItem.status != "completed",
                    WorkItem.status != "cancelled",
                    WorkItem.delivery_confidence.isnot(None),
                    WorkItem.delivery_confidence < Decimal("0.50"),
                )
            )
        )
        .scalars()
        .all()
    )
    escalations = []
    for item in items:
        if await _escalation_exists(session, item.id):
            continue
        escalations.append(
            _new_escalation(
                item,
                root_cause=f"Commitment '{item.title}' delivery confidence below 0.50.",
                target_role="dept_head",
                sla_days=2,
                recommended_actions=[
                    {
                        "action": "assess_risk",
                        "detail": "Assess schedule/resource risk and propose mitigation.",
                    }
                ],
                required_decision="mitigation or scope adjustment",
            )
        )
    return escalations


async def _esc2_hse(session: AsyncSession) -> list[Escalation]:
    items = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.hse_critical.is_(True),
                    WorkItem.status != "completed",
                    WorkItem.status != "cancelled",
                    WorkItem.delivery_confidence.isnot(None),
                    WorkItem.delivery_confidence < Decimal("0.70"),
                )
            )
        )
        .scalars()
        .all()
    )
    escalations = []
    for item in items:
        if await _escalation_exists(session, item.id):
            continue
        escalations.append(
            _new_escalation(
                item,
                root_cause=f"HSE-critical item '{item.title}' delivery confidence below 0.70.",
                target_role="hsse_manager",
                sla_days=1,
                recommended_actions=[
                    {
                        "action": "investigate",
                        "detail": "Investigate the delay cause and available controls.",
                    }
                ],
                required_decision="control action or escalation to dept head",
            )
        )
    return escalations


async def _esc3_objectives(session: AsyncSession) -> list[Escalation]:
    """ESC-3 v1: objectives with delivery confidence below 0.80 (drop proxy)."""
    items = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type == WorkType.OBJECTIVE,
                    WorkItem.status != "completed",
                    WorkItem.status != "cancelled",
                    WorkItem.delivery_confidence.isnot(None),
                    WorkItem.delivery_confidence < Decimal("0.80"),
                )
            )
        )
        .scalars()
        .all()
    )
    escalations = []
    for item in items:
        if await _escalation_exists(session, item.id):
            continue
        escalations.append(
            _new_escalation(
                item,
                root_cause=f"Objective '{item.title}' delivery confidence below 0.80.",
                target_role="executive_sponsor",
                sla_days=3,
                recommended_actions=[
                    {
                        "action": "review",
                        "detail": "Review strategic alignment and intervention options.",
                    }
                ],
                required_decision="approve mitigation or reprioritisation",
            )
        )
    return escalations


async def _esc4_shortage(session: AsyncSession) -> list[Escalation]:
    shortages = await capacity_engine.competency_shortage(session, utcnow().date())
    escalations = []
    for shortage in shortages:
        competency_id = shortage["competency_id"]
        item = (
            (await session.execute(select(Competency).where(Competency.id == competency_id)))
            .scalars()
            .first()
        )
        if item is None:
            continue
        if await _escalation_exists(session, None, competency_id):
            continue
        escalations.append(
            _new_escalation(
                None,
                root_cause=f"Sustained competency shortage on '{item.name}'.",
                target_role="resource_manager",
                sla_days=5,
                recommended_actions=[
                    {
                        "action": "backfill",
                        "detail": "Backfill from contractors, adjust scope or re-prioritise work.",
                    }
                ],
                required_decision="backfill decision or scope adjustment",
                competency_id=competency_id,
            )
        )
    return escalations


async def generate_escalations(session: AsyncSession) -> list[Escalation]:
    """Create escalations per the configured rules (plan §9.6, T7.6)."""
    created: list[Escalation] = []
    created.extend(await _esc1_commitments(session))
    created.extend(await _esc2_hse(session))
    created.extend(await _esc3_objectives(session))
    created.extend(await _esc4_shortage(session))
    if created:
        session.add_all(created)
        await session.commit()
    return created
