"""Assistant conversation persistence (plan Phase 8, T8.3).

Persists Ask-EIL conversations per principal so multi-turn chats survive
reloads (T8.3 conversation logging).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin


class AssistantConversation(IdMixin, TimestampMixin, Base):
    """One persisted Ask-EIL conversation (user ↔ assistant messages)."""

    __tablename__ = "assistant_conversation"

    principal: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
