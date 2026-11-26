"""Link proposals (plan §8.7, T4.8): retrieve → rerank → proposed work_link (status='proposed')."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import Gateway
from eil.ai.models import AiSuggestion
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import RerankLinksOutput
from eil.modules.execution.models import WorkItem, WorkLink, WorkType

_RETRIEVE_TYPES = [WorkType.OBJECTIVE, WorkType.PROJECT, WorkType.PROGRAM, WorkType.MILESTONE]
MAX_LINKS = 5


async def propose_links(
    gateway: Gateway,
    session: AsyncSession,
    item: WorkItem,
    *,
    max_links: int = MAX_LINKS,
    alias: str = "strong",
) -> list[WorkLink]:
    """Propose ``aligns_to``/``part_of`` links from ``item`` to existing entities."""
    entities = [
        {"id": str(target.id), "title": target.title, "type": str(target.type)}
        for target in (
            (await session.execute(select(WorkItem).where(WorkItem.type.in_(_RETRIEVE_TYPES))))
            .scalars()
            .all()
        )
    ]
    if not entities:
        return []
    prompt = prompt_registry.get("rerank_links")
    item_text = f"{item.title}: {item.description or item.title}"
    result: RerankLinksOutput = await gateway.structured(
        prompt,
        {"artifact_text": item_text, "entities_json": json.dumps(entities, ensure_ascii=False)},
        session=session,
        alias=alias,
    )
    created: list[WorkLink] = []
    for link in result.links[:max_links]:
        target = next((entry for entry in entities if entry["id"] == link.entity_id), None)
        if target is None:
            continue
        from uuid import UUID

        if (
            await session.execute(
                select(WorkLink).where(
                    WorkLink.src_id == item.id,
                    WorkLink.dst_id == UUID(target["id"]),
                    WorkLink.link_type == link.link_type,
                )
            )
        ).scalars().first() is not None:
            continue
        work_link = WorkLink(
            src_id=item.id,
            dst_id=UUID(target["id"]),
            link_type=link.link_type,
            weight=1,
            origin="ai",
            status="proposed",
            confidence=link.confidence,
        )
        session.add(work_link)
        created.append(work_link)
    await session.flush()
    return created


async def link_suggestions(
    session: AsyncSession, artifact_id: str | None = None
) -> list[AiSuggestion]:
    """Existing ``link`` suggestions (plan §8.7 §4 inbox 'duplicate/related panel')."""
    from uuid import UUID

    if artifact_id is None:
        return []
    rows = (
        (
            await session.execute(
                select(AiSuggestion)
                .where(
                    AiSuggestion.kind == "link",
                    AiSuggestion.status == "pending",
                    AiSuggestion.payload["artifact_id"].as_string() == UUID(artifact_id),
                )
                .order_by(AiSuggestion.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
