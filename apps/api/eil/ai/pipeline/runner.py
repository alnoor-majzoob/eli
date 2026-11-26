"""AI analysis runner (plan §8.7): the sync trigger for the extraction pipeline.

For each of a source's newest artifacts (when the source allows AI processing):
pass 1 ``detect_candidates`` → pass 2 ``structure_items`` → evidence-guard →
``extracted_item`` suggestions, plus an LLM ``owner_hint`` → deterministic
owner resolution → accepted ``owner`` suggestion.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import LLMError, get_gateway
from eil.ai.pipeline.artifacts import artifact_text
from eil.ai.pipeline.extraction import (
    create_extraction_suggestions,
    detect_candidates,
    structure_items,
)
from eil.ai.prompts.registry import prompt_registry
from eil.modules.integration.models import ApprovedSource, SourceArtifact

MAX_ARTIFACTS = 5


async def run_ai_analysis(
    session: AsyncSession, source: ApprovedSource, *, max_artifacts: int = MAX_ARTIFACTS
) -> dict[str, int]:
    """Create extraction + owner suggestions for the newest source artifacts."""
    if not source.ai_processing_allowed:
        return {"artifacts": 0, "suggestions": 0, "owner_suggestions": 0}
    gateway = get_gateway()
    artifacts = (
        (
            await session.execute(
                select(SourceArtifact)
                .where(SourceArtifact.source_id == source.id)
                .order_by(SourceArtifact.ingested_at.desc(), SourceArtifact.id.desc())
                .limit(max_artifacts)
            )
        )
        .scalars()
        .all()
    )
    created = 0
    owner_created = 0
    for artifact in artifacts:
        text = await artifact_text(artifact)
        if not text.strip():
            continue
        try:
            candidates = await detect_candidates(gateway, session, text, artifact=artifact)
            if not candidates:
                continue
            structured = await structure_items(gateway, session, text, candidates)
            suggestions = await create_extraction_suggestions(
                session, artifact, structured, prompt_registry.get("structure_items")
            )
            created += len(suggestions)
        except LLMError:
            continue
    await session.commit()
    return {"artifacts": len(artifacts), "suggestions": created, "owner_suggestions": owner_created}
