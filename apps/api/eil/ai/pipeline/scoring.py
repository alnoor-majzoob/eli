"""AI-assisted scoring: `score_assist@v1` → `ai_suggestion(kind="priority_scores")` (T5.2).

The deterministic score is always recomputed by
``eil.modules.prioritization.service.compute_score``; the AI proposal carries the
per-criterion scores + rationale + an explanation.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import get_gateway
from eil.ai.models import AiSuggestion
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import ScoreAssistOutput
from eil.modules.execution.models import WorkItem, WorkLink
from eil.modules.prioritization.models import ScoringModelCriterion
from eil.modules.prioritization.service import get_active_model


async def build_scoring_evidence(
    session: AsyncSession, work_item: WorkItem
) -> list[dict[str, Any]]:
    """Links (aligns_to/part_of/depends_on…) and regulatory flags as evidence."""
    evidence: list[dict[str, Any]] = []
    for link in (
        (await session.execute(select(WorkLink).where(WorkLink.src_id == work_item.id)))
        .scalars()
        .all()
    ):
        target = (
            (await session.execute(select(WorkItem).where(WorkItem.id == link.dst_id)))
            .scalars()
            .first()
        )
        if target is None:
            continue
        evidence.append(
            {"relation": link.link_type, "title": target.title, "kind": str(target.type)}
        )
    attributes = work_item.attributes or {}
    if attributes.get("regulatory_mandatory") or attributes.get("regulatory"):
        evidence.append({"relation": "regulatory", "flags": attributes.get("regulatory")})
    return evidence


async def propose_score_assist(
    session: AsyncSession, work_item: WorkItem, *, alias: str = "strong"
) -> dict[str, Any]:
    """Call ``score_assist`` for one item; returns {scores, explanation}."""
    model = await get_active_model(session)
    criteria = (
        (
            await session.execute(
                select(ScoringModelCriterion)
                .where(ScoringModelCriterion.model_id == model.id)
                .order_by(ScoringModelCriterion.criterion)
            )
        )
        .scalars()
        .all()
    )
    criteria_json = json.dumps(
        {
            criterion.criterion: {
                "weight": float(criterion.weight),
                "direction": criterion.direction,
                "anchored_scale": criterion.anchored_scale,
            }
            for criterion in criteria
        }
    )
    item_json = json.dumps(
        {"id": str(work_item.id), "title": work_item.title, "description": work_item.description}
    )
    evidence_json = json.dumps(await build_scoring_evidence(session, work_item))

    prompt = prompt_registry.get("score_assist")
    result: ScoreAssistOutput = await get_gateway().structured(
        prompt,
        {"item_json": item_json, "criteria_json": criteria_json, "evidence_json": evidence_json},
        session=session,
        alias=alias,
    )
    valid = {criterion.criterion for criterion in criteria}
    scores = {
        key: score_assist.score
        for key, score_assist in (result.scores or {}).items()
        if key in valid and score_assist.score in (1, 2, 3, 4, 5)
    }
    return {"scores": scores, "explanation": result.explanation}


async def create_priority_scores_suggestion(
    session: AsyncSession,
    work_item: WorkItem,
    proposals: dict[str, Any],
    *,
    model: str = "ai",
    prompt_version: str = "score_assist@v1",
) -> AiSuggestion:
    """Store the AI proposal as a pending ``priority_scores`` suggestion."""
    suggestion = AiSuggestion(
        kind="priority_scores",
        payload={
            "item_id": str(work_item.id),
            "scores": proposals["scores"],
            "explanation": proposals["explanation"],
        },
        model=model,
        prompt_version=prompt_version,
        status="pending",
    )
    session.add(suggestion)
    await session.flush()
    return suggestion
