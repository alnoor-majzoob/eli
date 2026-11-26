"""Ask EIL API (plan Phase 8, T8.3).

`POST /assistant/ask` — Ask EIL with read-only tool-calling; the response
carries the answer, the tool log and the entity citations. Optional SSE
streaming (`stream: true`) emits `tool_call` events as tools execute and a
final `result` event (T8.3 streaming).
`GET /assistant/conversations` + `GET /assistant/conversations/{id}` —
conversation logging read models (T8.3).
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.db import get_db
from eil.modules.assistant import service
from eil.modules.assistant.schemas import AskEilRequest, AssistantConversationRead
from eil.modules.identity.rbac import PermissionContext, require_permission
from eil.modules.seed_data import WORK_VIEW

router = APIRouter(tags=["assistant"])

CtxRead = Annotated[PermissionContext, Depends(require_permission(WORK_VIEW))]
Db = Annotated[AsyncSession, Depends(get_db)]


@router.post("/assistant/ask", response_model=None)
async def assistant_ask(
    ctx: CtxRead, session: Db, payload: AskEilRequest
) -> dict[str, Any] | StreamingResponse:
    kwargs: dict[str, Any] = {}
    if payload.max_turns is not None:
        kwargs["max_turns"] = payload.max_turns
    if payload.conversation_id is not None:
        kwargs["conversation_id"] = payload.conversation_id
    if payload.stream:
        return StreamingResponse(
            _stream_sse(session, ctx, payload, kwargs),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    return await service.ask_eil(session, ctx, payload.question, **kwargs)


async def _stream_sse(
    session: AsyncSession,
    ctx: PermissionContext,
    payload: AskEilRequest,
    kwargs: dict[str, Any],
) -> Any:
    """SSE stream: `tool_call` events + final `result` event (T8.3 streaming)."""
    events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_event(event: dict[str, Any]) -> None:
        await events.put(event)

    async def runner() -> None:
        try:
            result = await service.ask_eil(
                session, ctx, payload.question, on_event=on_event, **kwargs
            )
            await events.put({"type": "result", "data": result})
        except Exception as exc:  # surface stream errors to the client after headers
            await events.put({"type": "error", "data": {"detail": str(exc)}})
        finally:
            await events.put(None)

    task = asyncio.create_task(runner())
    try:
        while True:
            event = await events.get()
            if event is None:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"
    finally:
        if not task.done():
            task.cancel()
        await task


@router.get("/assistant/conversations")
async def assistant_conversations(ctx: CtxRead, session: Db) -> list[AssistantConversationRead]:
    """List the principal's assistant conversations (T8.3)."""
    conversations = await service.list_conversations(session, ctx)
    return [
        AssistantConversationRead.model_validate(conversation) for conversation in conversations
    ]


@router.get("/assistant/conversations/{conversation_id}")
async def assistant_conversation_detail(
    ctx: CtxRead, session: Db, conversation_id: UUID
) -> AssistantConversationRead:
    """Detail of one assistant conversation (T8.3)."""
    conversation = await service.get_conversation(session, ctx, conversation_id)
    return AssistantConversationRead.model_validate(conversation)
