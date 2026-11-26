"""Governance: segregation-of-duties rules, workflows and approvals."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin, utcnow


class SoDRule(IdMixin, TimestampMixin, Base):
    __tablename__ = "sod_rule"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class WorkflowDefinition(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_def"

    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (UniqueConstraint("key", "version", name="uq_workflow_def_key_version"),)


class WorkflowInstance(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_instance"

    definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_def.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_state: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    requested_by: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("work_item_id", "status", name="uq_workflow_instance_item_status"),
    )


class Approval(IdMixin, TimestampMixin, Base):
    __tablename__ = "approval"

    instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_instance.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[int] = mapped_column(default=1, nullable=False)
    approver_role: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    requested_by: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decided_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delegated_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    delegated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    delegated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("instance_id", "step", name="uq_approval_instance_step"),)


def new_decision_time() -> datetime:
    return utcnow()
