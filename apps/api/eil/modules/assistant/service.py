"""Ask EIL assistant service (plan Phase 8, T8.3 v1).

Read-only tool-calling over the enterprise data: the LLM calls tools
(`query_graph`, `get_capacity`, `list_commitments`, `get_risks`,
`explain_confidence`, `get_priorities`) and narrates the results with entity
citations. AI-off (R12) → graceful "unavailable" response; read-only tools only
(no tool calls inside tools — R6-style guard).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway import get_gateway
from eil.core.config import get_settings
from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.assistant.models import AssistantConversation
from eil.modules.capacity import engine as capacity_engine
from eil.modules.execution.models import WorkItem, WorkType
from eil.modules.graph.service import downstream_impact
from eil.modules.identity.rbac import PermissionContext
from eil.modules.metrics import service as metrics_service
from eil.modules.risk.explain import explain_confidence

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_graph",
            "description": "Downstream impact of an entity (affected work items).",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_capacity",
            "description": "Capacity overview: per-resource utilisation with RAG status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_commitments",
            "description": "Open commitments with due dates and delivery confidence.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_risks",
            "description": "Items at risk (low delivery confidence) and open escalations.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_confidence",
            "description": "Fact sheet for an item's delivery confidence.",
            "parameters": {
                "type": "object",
                "properties": {"item_id": {"type": "string"}},
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_priorities",
            "description": "Top-ranked priorities with score and override flags.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

SYSTEM_PROMPT = (
    "You are EIL, an enterprise execution assistant. Answer the user's question "
    "using the tools provided. Use the tools when they are relevant. Quote entity "
    "IDs from tool results as citations. Refuse politely anything you cannot "
    "answer or do not have tools for."
)


async def _execute_tool(
    session: AsyncSession, ctx: PermissionContext, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Read-only tool execution (no writes)."""
    if name == "query_graph":
        item_id = UUID(str(arguments["item_id"]))
        impact = await downstream_impact(session, ctx, item_id)
        return {"root_id": str(impact.root_id), "items": [row.model_dump() for row in impact.items]}
    if name == "get_capacity":
        overloads = await capacity_engine.detect_overloads(session, date.today())
        return {
            "overloads": [
                {
                    "resource_id": str(row["resource_id"]),
                    "week_start": row["week_start"],
                    "utilisation": float(row["utilisation"]),
                    "status": row["status"],
                }
                for row in overloads
            ]
        }
    if name == "list_commitments":
        limit = int(arguments.get("limit") or 20)
        items = (
            (
                await session.execute(
                    select(WorkItem)
                    .where(WorkItem.type == WorkType.COMMITMENT)
                    .order_by(WorkItem.planned_end)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return {
            "commitments": [
                {
                    "id": str(item.id),
                    "title": item.title,
                    "planned_end": str(item.planned_end) if item.planned_end else None,
                    "confidence": float(item.delivery_confidence or 0),
                }
                for item in items
            ]
        }
    if name == "get_risks":
        summary = await metrics_service.executive_summary(session, ctx)
        return {
            "at_risk": summary["at_risk"],
            "interventions": summary["interventions"],
        }
    if name == "explain_confidence":
        item_id = UUID(str(arguments["item_id"]))
        return await explain_confidence(session, ctx, item_id)
    if name == "get_priorities":
        summary = await metrics_service.executive_summary(session, ctx)
        return {"priorities": summary["priorities"]}
    raise AppError(400, "validation_error", "Validation error", f"Unknown tool '{name}'.")


def _collect_citations(tool_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in tool_log:
        output = entry["output"]
        candidates: list[str] = []
        if isinstance(output, dict):
            for key in ("item_id", "root_id"):
                if output.get(key):
                    candidates.append(str(output[key]))
            items = output.get("items")
            if isinstance(items, list):
                candidates.extend(
                    str(row["id"]) for row in items if isinstance(row, dict) and row.get("id")
                )
            for key in ("commitments", "at_risk", "priorities"):
                rows = output.get(key)
                if isinstance(rows, list):
                    candidates.extend(
                        str(row["item_id"] if row.get("item_id") else row.get("id"))
                        for row in rows
                        if isinstance(row, dict) and (row.get("item_id") or row.get("id"))
                    )
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                citations.append({"id": candidate, "source": entry["name"]})
    return citations


async def _conversation_history(
    session: AsyncSession, ctx: PermissionContext, conversation_id: UUID | None
) -> list[dict[str, Any]]:
    if conversation_id is None:
        return []
    conversation = await get_conversation(session, ctx, conversation_id)
    return [dict(message) for message in conversation.messages]


async def upsert_conversation(
    session: AsyncSession,
    ctx: PermissionContext,
    conversation_id: UUID,
    question: str,
    answer: str,
) -> AssistantConversation:
    """Append the question/answer exchange to the principal's conversation (T8.3)."""
    conversation = (
        await session.execute(
            select(AssistantConversation).where(AssistantConversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conversation is None or conversation.principal != ctx.principal.subject:
        raise AppError(404, "not_found", "Not found", "Conversation not found.")
    conversation.messages = [
        *conversation.messages,
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer},
    ]
    conversation.title = conversation.title or question[:120]
    conversation.updated_at = utcnow()
    session.add(conversation)
    await session.commit()
    return conversation


async def list_conversations(
    session: AsyncSession, ctx: PermissionContext, limit: int = 50
) -> list[AssistantConversation]:
    """List the principal's conversations, newest first (T8.3)."""
    return list(
        (
            await session.execute(
                select(AssistantConversation)
                .where(AssistantConversation.principal == ctx.principal.subject)
                .order_by(AssistantConversation.updated_at.desc(), AssistantConversation.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def get_conversation(
    session: AsyncSession, ctx: PermissionContext, conversation_id: UUID
) -> AssistantConversation:
    """Fetch one conversation scoped to the caller's principal (T8.3)."""
    conversation = (
        await session.execute(
            select(AssistantConversation).where(AssistantConversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conversation is None or conversation.principal != ctx.principal.subject:
        raise AppError(404, "not_found", "Not found", "Conversation not found.")
    return conversation


async def ask_eil(
    session: AsyncSession,
    ctx: PermissionContext,
    question: str,
    *,
    max_turns: int = 4,
    conversation_id: UUID | None = None,
    on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Ask EIL (plan Phase 8, T8.3): tool-calling over read-only tools.

    Conversation logging (T8.3): exchanges are persisted per principal.
    Streaming (T8.3): pass ``on_event`` to receive ``tool_call``/``answer`` events.
    """
    settings = get_settings()
    if not settings.ai_enabled:
        raise AppError(
            409, "not_available", "AI disabled", "Ask EIL is unavailable while AI is disabled."
        )
    history = await _conversation_history(session, ctx, conversation_id)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": question},
    ]
    tool_log: list[dict[str, Any]] = []
    answer = "The assistant reached the maximum number of tool calls."
    for _ in range(max_turns):
        result = (
            await get_gateway()
            .client()
            .chat(messages, alias="strong", temperature=0.2, tools=TOOL_DEFINITIONS)
        )
        if not result.tool_calls:
            answer = result.content or ""
            if on_event is not None:
                await on_event({"type": "answer", "text": answer})
            break
        assistant_calls = []
        for call in result.tool_calls:
            output = await _execute_tool(session, ctx, call.name, call.arguments)
            tool_log.append({"name": call.name, "arguments": call.arguments, "output": output})
            if on_event is not None:
                await on_event(
                    {
                        "type": "tool_call",
                        "name": call.name,
                        "arguments": call.arguments,
                        "output": output,
                    }
                )
            assistant_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
            )
            messages.append(
                {"role": "assistant", "content": result.content, "tool_calls": assistant_calls}
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(output, default=str),
                }
            )
    payload: dict[str, Any] = {
        "answer": answer,
        "tool_log": tool_log,
        "citations": _collect_citations(tool_log),
    }
    if conversation_id is not None:
        await upsert_conversation(session, ctx, conversation_id, question, answer)
        payload["conversation_id"] = str(conversation_id)
    else:
        conversation = AssistantConversation(
            principal=ctx.principal.subject,
            title=question[:120],
            messages=[
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ],
        )
        session.add(conversation)
        await session.commit()
        payload["conversation_id"] = str(conversation.id)
    return payload
