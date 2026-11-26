"""Executive metrics layer (plan Phase 8, T8.1).

Read models for the executive view (Scenario 5): committed work, priorities,
capacity constraints, at-risk items, strategic outcomes, interventions
required. Definitions documented in ``docs/metrics.md``; every widget carries
an ``as_of`` timestamp.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.capacity import engine as capacity_engine
from eil.modules.execution.models import WorkItem, WorkItemStatus, WorkType
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext
from eil.modules.risk.models import Escalation

LOW_CONFIDENCE = "red"
AT_RISK_CONFIDENCE = 0.5


def _as_naive_utc(value: datetime) -> datetime:
    """Normalise an aware/naive timestamp to the naive-UTC form stored on SQLite
    (naive on PostgreSQL); comparisons against stored values stay correct."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _visible(rows: Sequence[Any], cutoff: datetime) -> list[Any]:
    """Filter rows by ``updated_at <= cutoff`` (replay semantics, plan §10 T8.5)."""
    return [row for row in rows if _as_naive_utc(row.updated_at) <= cutoff]


async def executive_summary(
    session: AsyncSession, ctx: PermissionContext, as_of: datetime | None = None
) -> dict[str, Any]:
    """The executive summary read model (Scenario 5 acceptance, plan §11.5)."""
    as_of = as_of or datetime.now().astimezone()
    cutoff = _as_naive_utc(as_of)

    commitments = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type == WorkType.COMMITMENT,
                    WorkItem.status.notin_((WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)),
                )
            )
        )
        .scalars()
        .all()
    )
    commitments = _visible(commitments, cutoff)
    by_org_unit: dict[UUID | None, list[WorkItem]] = defaultdict(list)
    for commitment in commitments:
        by_org_unit[commitment.org_unit_id].append(commitment)
    avg_confidence = [
        float(item.delivery_confidence)
        for item in commitments
        if item.delivery_confidence is not None
    ]

    priorities = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type.in_((WorkType.DEMAND, WorkType.PROJECT, WorkType.OBJECTIVE)),
                    WorkItem.delivery_confidence.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    priorities = _visible(priorities, cutoff)
    priorities_read = sorted(
        (
            {
                "item_id": item.id,
                "title": item.title,
                "type": str(item.type),
                "confidence": float(str(item.delivery_confidence or 0)),
                "override": bool((item.attributes or {}).get("override")),
            }
            for item in priorities
            if item.delivery_confidence is not None
        ),
        key=lambda row: -row["confidence"] if isinstance(row["confidence"], (int, float)) else 0.0,
    )[:20]

    overloads = await capacity_engine.detect_overloads(session, cutoff.date())
    capacity_constraints = [
        {
            "resource_id": row["resource_id"],
            "week_start": row["week_start"],
            "utilisation": row["utilisation"],
            "status": row["status"],
        }
        for row in overloads[:10]
    ]

    at_risk_rows = _visible(
        (
            (
                await session.execute(
                    select(WorkItem).where(
                        WorkItem.type.in_(
                            (
                                WorkType.COMMITMENT,
                                WorkType.PROJECT,
                                WorkType.MILESTONE,
                                WorkType.OBJECTIVE,
                                WorkType.INITIATIVE,
                            )
                        ),
                        WorkItem.delivery_confidence.isnot(None),
                        WorkItem.delivery_confidence < 0.5,
                    )
                )
            )
            .scalars()
            .all()
        ),
        cutoff,
    )
    at_risk = []
    for item in at_risk_rows:
        at_risk.append(
            {
                "item_id": item.id,
                "title": item.title,
                "confidence": float(str(item.delivery_confidence or 0)),
            }
        )

    escalations = _visible(
        (
            (
                await session.execute(
                    select(Escalation)
                    .where(Escalation.acknowledged_at.is_(None))
                    .order_by(Escalation.due_at)
                )
            )
            .scalars()
            .all()
        ),
        cutoff,
    )
    interventions = [
        {
            "id": row.id,
            "root_cause": row.root_cause,
            "target_role": row.target_role,
            "due_at": row.due_at,
        }
        for row in escalations
    ]

    users = {row.id: row.name for row in (await session.execute(select(User.id, User.name))).all()}

    return {
        "as_of": as_of,
        "committed": {
            "total": len(commitments),
            "avg_confidence": sum(avg_confidence) / len(avg_confidence) if avg_confidence else None,
            "by_org_unit": [
                {
                    "org_unit_id": org_unit_id,
                    "count": len(rows),
                    "min_confidence": min(
                        (r.delivery_confidence for r in rows if r.delivery_confidence is not None),
                        default=None,
                    ),
                }
                for org_unit_id, rows in sorted(by_org_unit.items(), key=lambda kv: str(kv[0]))
            ],
        },
        "priorities": priorities_read,
        "capacity_constraints": capacity_constraints,
        "at_risk": at_risk,
        "strategic_outcomes": {
            "benefits_total": (
                await session.execute(
                    select(func.count())
                    .select_from(WorkItem)
                    .where(WorkItem.type == WorkType.BENEFIT)
                )
            ).scalar_one(),
            "objectives": [
                {
                    "item_id": item.id,
                    "title": item.title,
                    "confidence": float(item.delivery_confidence or 0),
                }
                for item in _visible(
                    (
                        (
                            await session.execute(
                                select(WorkItem).where(
                                    WorkItem.type == WorkType.OBJECTIVE,
                                    WorkItem.status.notin_(
                                        (WorkItemStatus.COMPLETED, WorkItemStatus.CANCELLED)
                                    ),
                                )
                            )
                        )
                        .scalars()
                        .all()
                    ),
                    cutoff,
                )
            ],
        },
        "interventions": interventions,
        "users": users,
    }
