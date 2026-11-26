"""Feedback loop (plan §8, T4.12): accept/edit/reject signals + weekly metrics."""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.models import AiSuggestion


async def record_feedback(session: AsyncSession, suggestion_id: UUID, action: str) -> None:
    """Store an accept/edit/reject signal on the suggestion row."""
    suggestion = (
        (await session.execute(select(AiSuggestion).where(AiSuggestion.id == suggestion_id)))
        .scalars()
        .first()
    )
    if (
        suggestion is not None
        and suggestion.status == "pending"
        and action in ("accepted", "edited", "rejected")
    ):
        suggestion.status = action
        suggestion.review_reason = f"Feedback: {action}."
        session.add(suggestion)
        await session.commit()


async def weekly_feedback_metrics(session: AsyncSession) -> dict[str, int]:
    """Aggregate suggestion feedback by kind:status for the weekly metrics job."""
    rows = (await session.execute(select(AiSuggestion.kind, AiSuggestion.status))).all()
    counts = Counter((row.kind, row.status) for row in rows)
    return {f"{kind}:{status}": count for (kind, status), count in sorted(counts.items())}
