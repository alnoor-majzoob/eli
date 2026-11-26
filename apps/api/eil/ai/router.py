"""AI Inbox API (plan §8.7, T4.9): pending suggestions with filters; detail with
source excerpt + highlighted evidence; accept / edit-and-accept / reject / bulk."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.models import AiSuggestion
from eil.ai.pipeline.promotion import accept_suggestion
from eil.ai.schemas import (
    AiSuggestionAcceptBody,
    AiSuggestionBulkBody,
    AiSuggestionBulkResult,
    AiSuggestionDetail,
    AiSuggestionRead,
    AiSuggestionRejectBody,
)
from eil.core.db import get_db
from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.execution.models import WorkItem
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.integration.models import SourceArtifact
from eil.modules.seed_data import AI_REVIEW, WORK_VIEW

router = APIRouter(tags=["ai"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
CtxWrite = Annotated[PermissionContext, Depends(require_permission(AI_REVIEW))]
Db = Annotated[AsyncSession, Depends(get_db)]


async def _load_suggestion(session: AsyncSession, suggestion_id: UUID) -> AiSuggestion:
    suggestion = (
        (await session.execute(select(AiSuggestion).where(AiSuggestion.id == suggestion_id)))
        .scalars()
        .first()
    )
    if suggestion is None:
        raise AppError(404, "not_found", "Not found", "Suggestion not found.")
    return suggestion


@router.get("/ai/suggestions", response_model=list[AiSuggestionRead])
async def ai_suggestions(
    ctx: CtxRead,
    session: Db,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[AiSuggestionRead]:
    filters: list = []
    if status:
        filters.append(AiSuggestion.status == status)
    if kind:
        filters.append(AiSuggestion.kind == kind)
    rows = (
        (
            await session.execute(
                select(AiSuggestion)
                .where(*filters)
                .order_by(AiSuggestion.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [AiSuggestionRead.model_validate(row) for row in rows]


@router.get("/ai/suggestions/{suggestion_id}", response_model=AiSuggestionDetail)
async def ai_suggestion_detail(
    suggestion_id: UUID, ctx: CtxRead, session: Db
) -> AiSuggestionDetail:
    suggestion = await _load_suggestion(session, suggestion_id)
    artifact = None
    artifact_id = suggestion.payload.get("artifact_id")
    if artifact_id:
        artifact = (
            (
                await session.execute(
                    select(SourceArtifact).where(SourceArtifact.id == UUID(artifact_id))
                )
            )
            .scalars()
            .first()
        )
    reviewer = None
    if suggestion.reviewed_by:
        reviewer = (
            await session.execute(
                select(WorkItem).where(WorkItem.id == suggestion.resulting_entity)
            )
        ).scalar_one_or_none()
    excerpt = None
    if artifact is not None:
        payload = artifact.payload or {}
        excerpt = payload.get("body") or payload.get("text") or artifact.title
    return AiSuggestionDetail(
        id=str(suggestion.id),
        kind=suggestion.kind,
        status=suggestion.status,
        payload=suggestion.payload,
        evidence=suggestion.evidence,
        confidence=suggestion.confidence,
        model=suggestion.model,
        prompt_version=suggestion.prompt_version,
        source_artifact_id=artifact_id,
        source_excerpt=(str(excerpt)[:3000] if excerpt else None),
        reviewer_name=reviewer.title if reviewer else None,
        reviewed_at=suggestion.reviewed_at,
        created_at=suggestion.created_at,
    )


@router.post("/ai/suggestions/{suggestion_id}/accept", response_model=AiSuggestionRead)
async def ai_suggestion_accept(
    suggestion_id: UUID,
    ctx: CtxWrite,
    session: Db,
    payload: AiSuggestionAcceptBody | None = Body(default=None),
) -> AiSuggestionRead:
    suggestion = await _load_suggestion(session, suggestion_id)
    await accept_suggestion(
        session,
        ctx,
        suggestion.id,
        edited=payload.payload if payload else None,
    )
    return AiSuggestionRead.model_validate(suggestion)


@router.post("/ai/suggestions/{suggestion_id}/reject", response_model=AiSuggestionRead)
async def ai_suggestion_reject(
    suggestion_id: UUID,
    ctx: CtxWrite,
    session: Db,
    payload: AiSuggestionRejectBody,
) -> AiSuggestionRead:
    suggestion = await _load_suggestion(session, suggestion_id)
    if suggestion.status != "pending":
        raise AppError(409, "conflict", "Conflict", f"Suggestion already {suggestion.status}.")
    suggestion.status = "rejected"
    suggestion.review_reason = payload.reason
    suggestion.reviewed_by = ctx.user.id
    suggestion.reviewed_at = utcnow()
    session.add(suggestion)
    await session.commit()
    return AiSuggestionRead.model_validate(suggestion)


@router.post("/ai/suggestions/bulk", response_model=AiSuggestionBulkResult)
async def ai_suggestions_bulk(
    ctx: CtxWrite, session: Db, payload: AiSuggestionBulkBody
) -> AiSuggestionBulkResult:
    accepted: list[UUID] = []
    rejected: list[UUID] = []
    errors: dict[str, str] = {}
    for item in payload.items:
        suggestion = (
            (
                await session.execute(
                    select(AiSuggestion).where(AiSuggestion.id == item.suggestion_id)
                )
            )
            .scalars()
            .first()
        )
        if suggestion is None:
            errors[str(item.suggestion_id)] = "Suggestion not found."
            continue
        if item.action == "accept":
            try:
                await accept_suggestion(session, ctx, suggestion.id, execute_links=False)
                accepted.append(suggestion.id)
            except AppError as exc:
                errors[str(suggestion.id)] = str(exc.detail)
        else:
            if suggestion.status == "pending":
                suggestion.status = "rejected"
                suggestion.review_reason = item.reason or "Rejected via bulk action."
                suggestion.reviewed_by = ctx.user.id
                suggestion.reviewed_at = utcnow()
                session.add(suggestion)
                rejected.append(suggestion.id)
            else:
                errors[str(suggestion.id)] = f"Already {suggestion.status}."
    await session.commit()
    return AiSuggestionBulkResult(accepted=accepted, rejected=rejected, errors=errors)


__all__ = ["router"]
