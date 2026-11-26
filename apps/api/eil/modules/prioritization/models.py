"""Scoring models (plan §9.1, Phase 5, T5.1)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin


class ScoringModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "scoring_model"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gating_floor_tier: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )


class ScoringModelCriterion(IdMixin, TimestampMixin, Base):
    __tablename__ = "scoring_model_criterion"

    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("scoring_model.id", ondelete="CASCADE"), nullable=False
    )
    criterion: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    anchored_scale: Mapped[dict] = mapped_column(JSON, nullable=False)
    gating: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "model_id", "criterion", name="uq_scoring_model_criterion_model_criterion"
        ),
        CheckConstraint("direction IN ('benefit', 'cost')", name="ck_scoring_criterion_direction"),
    )


class Score(IdMixin, TimestampMixin, Base):
    __tablename__ = "score"

    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    model_id: Mapped[UUID] = mapped_column(
        ForeignKey("scoring_model.id", ondelete="CASCADE"), nullable=False
    )
    scores: Mapped[dict] = mapped_column(JSON, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 3), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ScoreOverride(IdMixin, TimestampMixin, Base):
    __tablename__ = "score_override"

    score_id: Mapped[UUID] = mapped_column(
        ForeignKey("score.id", ondelete="CASCADE"), nullable=False
    )
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    original_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    approver_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
