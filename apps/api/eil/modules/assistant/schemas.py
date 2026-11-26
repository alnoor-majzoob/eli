"""Assistant schemas (plan Phase 8, T8.3).

- ``AskEilRequest`` — extended for conversation logging (``conversation_id``)
  and streaming (``stream``).
- ``AssistantConversationRead`` — read model for conversation endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AskEilRequest(BaseModel):
    question: str
    max_turns: int | None = None
    conversation_id: UUID | None = None
    stream: bool = False


class AssistantConversationRead(BaseModel):
    id: UUID
    title: str | None
    messages: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
