"""AI models (plan §7.3, Phase 4): ``ai_suggestion``, ``llm_call`` telemetry."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin

SUGGESTION_KINDS: tuple[str, ...] = (
    "extracted_item",
    "link",
    "duplicate",
    "priority_scores",
    "owner",
    "mitigation",
)
SUGGESTION_STATUSES: tuple[str, ...] = (
    "pending",
    "accepted",
    "edited",
    "rejected",
    "superseded",
)
LLM_CALL_STATUSES: tuple[str, ...] = ("ok", "retried", "repaired", "failed", "replayed")


class AiSuggestion(IdMixin, TimestampMixin, Base):
    """An AI-generated proposal a human can accept, edit or reject."""

    __tablename__ = "ai_suggestion"

    kind: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    llm_call_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("llm_call.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_entity: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_item.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','accepted','edited','rejected','superseded')",
            name="ck_ai_suggestion_status",
        ),
    )


class LlmCall(IdMixin, Base):
    """Telemetry row for every LLM call (plan §8.8)."""

    __tablename__ = "llm_call"

    purpose: Mapped[str] = mapped_column(String(50), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_artifact.id"), nullable=True
    )
    redaction_applied: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
