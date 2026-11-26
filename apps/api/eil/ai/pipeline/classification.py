"""Classification (plan §8.6, §8.7): taxonomy-constrained classification → ai_suggestion."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import Gateway
from eil.ai.models import AiSuggestion
from eil.ai.pipeline.taxonomy import taxonomy_json
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import ClassificationOutput, ClassifyItemOutput


async def classify_item(
    gateway: Gateway,
    session: AsyncSession,
    item: dict[str, Any],
    *,
    alias: str = "fast",
) -> list[ClassificationOutput]:
    """Call ``classify_item`` for one item against the taxonomy."""
    prompt = prompt_registry.get("classify_item")
    result: ClassifyItemOutput = await gateway.structured(
        prompt,
        {"item_json": json.dumps(item, default=str), "taxonomy_json": taxonomy_json()},
        session=session,
        alias=alias,
    )
    return list(result.items)


async def create_classification_suggestions(
    session: AsyncSession,
    items: list[dict[str, Any]],
    classifications: list[ClassificationOutput],
) -> list[AiSuggestion]:
    suggestions: list[AiSuggestion] = []
    for item, classification in zip(items, classifications, strict=False):
        suggestion = AiSuggestion(
            kind="classification",
            payload={
                "item_id": item["id"],
                "type": classification.type,
                "category": classification.category,
                "department": classification.department,
                "hse_critical": classification.hse_critical,
                "regulatory": classification.regulatory,
                "reasons": classification.reasons,
            },
            confidence=classification.confidence,
            model="ai",
            prompt_version=prompt_registry.get("classify_item").telemetry_version(),
            status="pending",
        )
        session.add(suggestion)
        suggestions.append(suggestion)
    await session.flush()
    return suggestions
