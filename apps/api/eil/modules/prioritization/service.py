"""Deterministic scoring engine (plan §9.1, Phase 5, T5.1).

Default criteria/weights/directions are per plan §9.1; the model (criteria,
weights, directions, anchored scales) is versioned and editable via
``ScoringModel``/``ScoringModelCriterion`` (admin UI — T5.1). Score:

```
score = 100 x sum(w_i x n_i)   # n_i = (s_i - 1) / 4; cost criteria use 1 - n_i
tier  = tier_from_thresholds(score)
if hse_critical or regulatory_mandatory: tier = min(tier, floor_tier)
```
Per-criterion inputs come from ``work_item.attributes["scores"]`` (human-confirmed
or AI-proposed — the score is always recomputed deterministically here).
"""

from __future__ import annotations

from collections import OrderedDict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.modules.audit.service import record_audit
from eil.modules.execution.models import WorkItem
from eil.modules.graph.cache import graph_cache
from eil.modules.identity.rbac import PermissionContext
from eil.modules.prioritization.models import (
    Score,
    ScoreOverride,
    ScoringModel,
    ScoringModelCriterion,
)

DEFAULT_CRITERIA: tuple[tuple[str, float, str], ...] = (
    ("strategic_alignment", 0.20, "benefit"),
    ("business_value", 0.15, "benefit"),
    ("financial_impact", 0.12, "benefit"),
    ("operational_impact", 0.10, "benefit"),
    ("hse_criticality", 0.18, "benefit"),
    ("risk", 0.08, "benefit"),
    ("urgency", 0.07, "benefit"),
    ("dependency", 0.05, "benefit"),
    ("resource_constraint", 0.05, "cost"),
)

DEFAULT_ANCHORED_SCALE: dict[str, str] = {
    "1": "Negligible impact — no measurable effect.",
    "2": "Low impact — minor measurable effect.",
    "3": "Moderate impact — noticeable but contained.",
    "4": "High impact — significant measurable effect.",
    "5": "Critical impact — systemic, exceeding all expectations.",
}

DEFAULT_TIER_THRESHOLDS: tuple[tuple[int, Decimal], ...] = (
    (75, Decimal("1")),
    (55, Decimal("2")),
    (35, Decimal("3")),
    (0, Decimal("4")),
)

_VALID_SCORES = frozenset({1, 2, 3, 4, 5})


def tier_from_score(score: Decimal, thresholds: tuple = DEFAULT_TIER_THRESHOLDS) -> int:
    for score_threshold, tier in thresholds:
        if score >= Decimal(score_threshold):
            return int(tier)
    return len(thresholds)


def _normalise(score: int, direction: str) -> Decimal:
    n = Decimal(score - 1) / Decimal(4)
    return n if direction == "benefit" else Decimal(1) - n


def _regulatory_mandatory(work_item: WorkItem) -> bool:
    attributes = work_item.attributes or {}
    return bool(attributes.get("regulatory_mandatory") or attributes.get("regulatory"))


async def get_active_model(session: AsyncSession) -> ScoringModel:
    model = (
        (
            await session.execute(
                select(ScoringModel)
                .where(ScoringModel.is_active.is_(True))
                .order_by(ScoringModel.version.desc(), ScoringModel.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if model is not None:
        return model
    model = ScoringModel(
        name="Default",
        version="v1",
        effective_from=None,
        description="Plan §9.1 default scoring model.",
        is_active=True,
        gating_floor_tier=1,
    )
    session.add(model)
    await session.flush()
    for criterion, weight, direction in DEFAULT_CRITERIA:
        session.add(
            ScoringModelCriterion(
                model_id=model.id,
                criterion=criterion,
                weight=Decimal(str(weight)),
                direction=direction,
                anchored_scale=dict(DEFAULT_ANCHORED_SCALE),
                gating=False,
            )
        )
    await session.flush()
    return model


async def load_criteria(session: AsyncSession, model_id: Any) -> list[ScoringModelCriterion]:
    rows = (
        (
            await session.execute(
                select(ScoringModelCriterion)
                .where(ScoringModelCriterion.model_id == model_id)
                .order_by(ScoringModelCriterion.criterion)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def compute_score(
    session: AsyncSession,
    work_item: WorkItem,
    model: ScoringModel | None = None,
    *,
    rationale: dict[str, Any] | None = None,
) -> Score:
    """Recompute the deterministic score and upsert the ``Score`` row."""
    model = model or await get_active_model(session)
    criteria = await load_criteria(session, model.id)
    attribute_scores = (work_item.attributes or {}).get("scores") or {}
    scores: dict[str, int] = OrderedDict()
    weighted_sum = Decimal("0")
    for criterion_row in criteria:
        raw = attribute_scores.get(criterion_row.criterion)
        score_value = int(raw) if raw in _VALID_SCORES else 3
        scores[criterion_row.criterion] = score_value
        weighted_sum += Decimal(str(criterion_row.weight)) * _normalise(
            score_value, criterion_row.direction
        )
    total = Decimal("100") * weighted_sum
    tier = tier_from_score(total)
    gating = work_item.hse_critical or _regulatory_mandatory(work_item)
    if gating:
        tier = min(tier, int(model.gating_floor_tier or 1))

    score_row = (
        (await session.execute(select(Score).where(Score.work_item_id == work_item.id)))
        .scalars()
        .first()
    )
    if score_row is None:
        score_row = Score(
            work_item_id=work_item.id,
            model_id=model.id,
            scores=scores,
            score=total,
            tier=tier,
            rationale=rationale,
        )
        session.add(score_row)
    else:
        score_row.model_id = model.id
        score_row.scores = scores
        score_row.score = total
        score_row.tier = tier
        score_row.rationale = rationale
    await session.commit()
    return score_row


async def apply_override(
    session: AsyncSession,
    ctx: PermissionContext,
    work_item_id: Any,
    tier: int,
    justification: str,
    approver_id: Any,
) -> ScoreOverride:
    """Apply a human-approved priority override (plan §10, Phase 5, T5.1/T5.3).

    The board tier becomes the new tier while the original calculated tier is
    preserved on the override. The original calculated score is never
    recomputed here — the deterministic engine recomputes it when inputs
    change, and each override is audited with its original value.
    """
    if tier not in (1, 2, 3, 4):
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            "tier must be an integer between 1 and 4.",
        )
    work_item = (
        (await session.execute(select(WorkItem).where(WorkItem.id == work_item_id)))
        .scalars()
        .first()
    )
    if work_item is None:
        raise AppError(404, "not_found", "Not found", "Work item not found.")
    if ctx.scope == "own_org" and work_item.org_unit_id != ctx.user.org_unit_id:
        raise AppError(404, "not_found", "Not found", "Work item not found.")
    score = (
        (await session.execute(select(Score).where(Score.work_item_id == work_item_id)))
        .scalars()
        .first()
    )
    if score is None:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            "The work item has no calculated score to override.",
        )
    original_tier = score.tier
    override = ScoreOverride(
        score_id=score.id,
        tier=tier,
        original_tier=original_tier,
        justification=justification,
        approver_id=approver_id,
    )
    session.add(override)
    score.tier = tier
    await session.commit()
    graph_cache.invalidate()
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="priority.overridden",
        entity_type="score",
        entity_id=score.id,
        org_unit_id=work_item.org_unit_id,
        before={"tier": original_tier},
        after={"tier": tier, "original_tier": original_tier},
        reason=justification,
    )
    await session.commit()
    return override
