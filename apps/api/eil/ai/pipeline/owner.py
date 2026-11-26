"""Owner resolution (plan §8.5, §8.7): fuzzy match against the resource directory."""

from __future__ import annotations

from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import Gateway
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import OwnerCandidate, OwnerSuggestionOutput
from eil.modules.identity.models import User

MATCH_THRESHOLD = 0.6


async def load_users(session: AsyncSession) -> list[User]:
    return list((await session.execute(select(User))).scalars().all())


async def detect_owner_hint(
    gateway: Gateway, session: AsyncSession, artifact_text_value: str, *, alias: str = "strong"
) -> list[OwnerCandidate]:
    """LLM extracts owner hints (names/roles) from the artifact (plan §8.7)."""
    prompt = prompt_registry.get("detect_owner_hint")
    result: OwnerSuggestionOutput = await gateway.structured(
        prompt, {"artifact_text": artifact_text_value}, session=session, alias=alias
    )
    return list(result.candidates)


def resolve_owner(
    candidates: list[OwnerCandidate],
    users: list[User],
    attendees: list[str] | None = None,
    threshold: float = MATCH_THRESHOLD,
) -> OwnerCandidate | None:
    """Fuzzy-match hints against the resource directory; attendees prioritised."""
    attendee_set: set[str] = set(attendees or [])
    best: tuple[float, OwnerCandidate] | None = None
    for candidate in candidates:
        for user in users:
            name = (user.name or user.subject).lower()
            ratio = SequenceMatcher(None, candidate.name.lower(), name).ratio()
            if candidate.name.lower() in name or name in candidate.name.lower():
                ratio = max(ratio, 0.85)
            if user.name in attendee_set:
                ratio += 0.15
            if ratio < threshold:
                continue
            if best is None or ratio > best[0]:
                best = (ratio, candidate)
    return best[1] if best is not None else None
