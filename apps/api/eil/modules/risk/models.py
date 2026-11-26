"""Predictive execution models (plan §7.1, Phase 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin

ESCALATION_STATUSES = ("open", "acknowledged", "closed")


class Escalation(IdMixin, TimestampMixin, Base):
    """Management escalations created by the escalation rules (plan §9.6)."""

    __tablename__ = "escalation"

    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=True, index=True
    )
    competency_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("competency.id", ondelete="CASCADE"), nullable=True, index=True
    )
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    impact_cascade: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    required_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_role: Mapped[str] = mapped_column(String(50), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sla_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    acknowledged_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('open','acknowledged','closed')", name="ck_escalation_status"),
    )
