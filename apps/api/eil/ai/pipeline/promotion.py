"""Promotion service (plan §8, T4.10): accept → WorkItem + derived_from + back-reference + audit.

Accepting an extracted-item suggestion creates a ``task``/``commitment``/``risk``/
``decision``/``milestone`` with a ``derived_from`` link to the source artifact, a
``ai_suggestion`` back-reference on the suggestion, an owner applied when the LLM
hint resolved to a real resource, a pending classification suggestion, a hash-chained
audit entry and graph-cache invalidation.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import get_gateway
from eil.ai.models import AiSuggestion
from eil.ai.pipeline.classification import classify_item
from eil.ai.pipeline.links import propose_links
from eil.ai.pipeline.owner import load_users, resolve_owner
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import OwnerCandidate
from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.audit.service import record_audit
from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.graph.cache import graph_cache
from eil.modules.identity.rbac import PermissionContext
from eil.modules.integration.models import SourceArtifact

_EXTRACTED_TYPES: dict[str, WorkType] = {
    "task": WorkType.TASK,
    "commitment": WorkType.COMMITMENT,
    "risk": WorkType.RISK,
    "decision": WorkType.DECISION,
    "milestone": WorkType.MILESTONE,
}


async def _load_work_item(session: AsyncSession, item_id: Any) -> WorkItem | None:
    if item_id is None:
        return None
    return (
        (await session.execute(select(WorkItem).where(WorkItem.id == UUID(str(item_id)))))
        .scalars()
        .first()
    )


async def _promote_extracted(
    session: AsyncSession, ctx: PermissionContext, suggestion: AiSuggestion, payload: dict[str, Any]
) -> WorkItem:
    work_type = _EXTRACTED_TYPES.get(str(payload.get("kind", "")), WorkType.TASK)
    item = WorkItem(
        type=work_type,
        title=str(payload["title"]),
        description=payload.get("summary") or None,
        status="active",
        origin="ai_extracted",
        attributes={
            "canonical_type": "extracted_item",
            "source_type": "ai",
            "ai_suggestion_id": str(suggestion.id),
        },
        priority_tier=payload.get("priority"),
        hse_critical=bool(payload.get("hse_critical")),
        created_by=ctx.user.id,
    )
    session.add(item)
    await session.flush()

    artifact_id = payload.get("artifact_id")
    if artifact_id:
        aid = UUID(str(artifact_id))
        artifact = await session.get(SourceArtifact, aid)
        if artifact is not None:
            attrs = dict(item.attributes or {})
            attrs["source_artifact_id"] = str(artifact.id)
            attrs["source_id"] = str(artifact.source_id)
            attrs["source_external_id"] = artifact.external_id
            attrs["source_kind"] = artifact.kind
            item.attributes = attrs
            session.add(item)

    owner_hint = payload.get("owner_hint")
    if owner_hint:
        users = await load_users(session)
        candidates = [
            OwnerCandidate(
                user_id=str(user.id),
                name=user.name or user.subject,
                reason=str(owner_hint),
                score=1.0,
            )
            for user in users
        ]
        owner = resolve_owner(candidates, users)
        if owner is not None:
            item.owner_id = UUID(owner.user_id)
            session.add(item)
            session.add(
                AiSuggestion(
                    kind="owner",
                    payload={
                        "item_id": str(item.id),
                        "owner_id": owner.user_id,
                        "name": owner.name,
                        "reason": owner.reason,
                    },
                    model="ai",
                    prompt_version="owner@v1",
                    status="accepted",
                    resulting_entity=item.id,
                    reviewed_by=ctx.user.id,
                    reviewed_at=utcnow(),
                    review_reason="Applied at extraction acceptance.",
                )
            )

    session.add(
        AiSuggestion(
            kind="classification",
            payload={"item_id": str(item.id)},
            model="ai",
            prompt_version=prompt_registry.get("classify_item").telemetry_version(),
            status="pending",
        )
    )
    await session.flush()
    return item


async def _promote_link(
    session: AsyncSession, suggestion: AiSuggestion, payload: dict[str, Any]
) -> None:
    session.add(
        WorkLink(
            src_id=UUID(str(payload["src_id"])),
            dst_id=UUID(str(payload["dst_id"])),
            link_type=str(payload.get("link_type", "related_to")),
            origin="ai",
            status="active",
            weight=1,
        )
    )
    await session.flush()


async def _promote_owner(session: AsyncSession, suggestion: AiSuggestion) -> WorkItem | None:
    item = await _load_work_item(session, suggestion.payload.get("item_id"))
    if item is not None and suggestion.payload.get("owner_id"):
        item.owner_id = UUID(str(suggestion.payload["owner_id"]))
        session.add(item)
        await session.flush()
    return item


async def _promote_classification(
    session: AsyncSession, ctx: PermissionContext, suggestion: AiSuggestion
) -> WorkItem | None:
    item = await _load_work_item(session, suggestion.payload.get("item_id"))
    if item is None:
        return None
    classifications = await classify_item(
        get_gateway(),
        session,
        {"id": str(item.id), "title": item.title, "summary": item.description},
    )
    classification = classifications[0] if classifications else None
    if classification is not None:
        attributes = dict(item.attributes or {})
        attributes["classification"] = {
            key: getattr(classification, key)
            for key in ("type", "category", "department", "hse_critical", "regulatory", "reasons")
            if getattr(classification, key) is not None
        }
        item.attributes = attributes
        if classification.type:
            item.type = classification.type
        session.add(item)
        suggestion.payload = {
            "item_id": str(item.id),
            **{
                key: getattr(classification, key)
                for key in (
                    "type",
                    "category",
                    "department",
                    "hse_critical",
                    "regulatory",
                    "reasons",
                )
            },
            "confidence": classification.confidence,
        }
        await session.flush()
    return item


async def accept_suggestion(
    session: AsyncSession,
    ctx: PermissionContext,
    suggestion_id: UUID,
    *,
    edited: dict[str, Any] | None = None,
    execute_links: bool = True,
) -> AiSuggestion:
    """Accept a suggestion (with optional edits); returns the suggestion row."""
    suggestion = (
        (await session.execute(select(AiSuggestion).where(AiSuggestion.id == suggestion_id)))
        .scalars()
        .first()
    )
    if suggestion is None:
        raise AppError(404, "not_found", "Not found", "Suggestion not found.")
    if suggestion.status != "pending":
        raise AppError(409, "conflict", "Conflict", f"Suggestion already {suggestion.status}.")

    payload = dict(suggestion.payload)
    if edited:
        payload.update(edited)
    suggestion.payload = payload

    item: WorkItem | None = None
    if suggestion.kind == "extracted_item":
        item = await _promote_extracted(session, ctx, suggestion, payload)
        suggestion.resulting_entity = item.id
    elif suggestion.kind == "link":
        await _promote_link(session, suggestion, payload)
    elif suggestion.kind == "owner":
        item = await _promote_owner(session, suggestion)
    elif suggestion.kind == "classification":
        item = await _promote_classification(session, ctx, suggestion)

    suggestion.status = "accepted"
    suggestion.reviewed_by = ctx.user.id
    suggestion.reviewed_at = utcnow()
    suggestion.review_reason = "Accepted." if edited is None else "Accepted with edits."
    session.add(suggestion)
    await session.commit()

    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="ai_suggestion.accepted",
        entity_type="ai_suggestion",
        entity_id=suggestion.id,
        reason=f"Accepted {suggestion.kind} suggestion.",
    )
    await session.commit()
    graph_cache.invalidate()

    if item is not None and execute_links:
        await propose_links(get_gateway(), session, item)

    return suggestion
