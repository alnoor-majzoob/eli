"""Extraction pipeline (plan §8.7, T4.4): detect -> structure -> merge.

Evidence guard -> extracted_item suggestions.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import Gateway
from eil.ai.models import AiSuggestion
from eil.ai.pipeline.artifacts import artifact_text
from eil.ai.pipeline.evidence import verify_evidence
from eil.ai.prompts.registry import PromptSpec, prompt_registry
from eil.ai.schemas import (
    CandidateOutput,
    DetectCandidatesOutput,
    StructuredItem,
    StructuredItemsOutput,
)


def merge_items(structured: list[StructuredItem]) -> list[StructuredItem]:
    """Deduplicate within an artifact by title; drop duplicates flagged by the model."""
    merged: list[StructuredItem] = []
    seen_titles: set[str] = set()
    for item in structured:
        if item.duplicate_of_index is not None:
            continue
        key = item.title.strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        merged.append(item)
    return merged


async def detect_candidates(
    gateway: Gateway,
    session: AsyncSession,
    artifact_text_value: str,
    *,
    artifact: Any = None,
    alias: str = "fast",
) -> list[CandidateOutput]:
    """Pass 1: detect candidates in the artifact text (plan §8.7)."""
    prompt = prompt_registry.get("detect_candidates")
    result: DetectCandidatesOutput = await gateway.structured(
        prompt, {"artifact_text": artifact_text_value}, session=session, alias=alias
    )
    return list(result.candidates)


async def structure_items(
    gateway: Gateway,
    session: AsyncSession,
    artifact_text_value: str,
    candidates: list[CandidateOutput],
    *,
    alias: str = "strong",
) -> list[StructuredItem]:
    """Pass 2: structure/normalise candidates with evidence (plan §8.7)."""
    prompt = prompt_registry.get("structure_items")
    result: StructuredItemsOutput = await gateway.structured(
        prompt,
        {"candidates_json": json.dumps([candidate.model_dump() for candidate in candidates])},
        session=session,
        alias=alias,
    )
    return list(result.items)


async def create_extraction_suggestions(
    session: AsyncSession,
    artifact: Any,
    items: list[StructuredItem],
    prompt: PromptSpec,
) -> list[AiSuggestion]:
    """Create ``extracted_item`` suggestions after the evidence-verification guard."""
    source_text = await artifact_text(artifact)
    suggestions: list[AiSuggestion] = []
    for item in merge_items(items):
        if not verify_evidence(source_text, item.evidence_quote):
            # Evidence guard: drop unverified extraction (hallucinated-evidence rate: 0).
            continue
        suggestion = AiSuggestion(
            kind="extracted_item",
            payload={
                "title": item.title,
                "summary": item.summary,
                "kind": item.kind,
                "priority": item.priority,
                "owner_hint": item.owner_hint,
                "due_phrase": item.due_phrase,
                "artifact_id": str(artifact.id),
            },
            evidence={"quote": item.evidence_quote, "speaker": item.speaker},
            confidence=item.confidence,
            model="ai",
            prompt_version=prompt.telemetry_version(),
            status="pending",
        )
        session.add(suggestion)
        suggestions.append(suggestion)
    await session.flush()
    return suggestions
