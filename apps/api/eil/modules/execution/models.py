"""Core execution entities: work items, links and benefit measurements.

The unified ``work_item`` table follows the plan's polymorphic schema: type-specific
fields live in ``attributes`` while the shared fields remain queryable and indexable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin, VersionMixin


class WorkType(StrEnum):
    OBJECTIVE = "objective"
    KEY_RESULT = "key_result"
    INITIATIVE = "initiative"
    DEMAND = "demand"
    PROGRAM = "program"
    PROJECT = "project"
    MILESTONE = "milestone"
    TASK = "task"
    COMMITMENT = "commitment"
    RISK = "risk"
    ISSUE = "issue"
    BENEFIT = "benefit"
    DECISION = "decision"


class WorkItemStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LinkType(StrEnum):
    PART_OF = "part_of"
    ALIGNS_TO = "aligns_to"
    DEPENDS_ON = "depends_on"
    FULFILS = "fulfils"
    REALIZES = "realizes"
    THREATENS = "threatens"
    MITIGATES = "mitigates"
    DUPLICATE_OF = "duplicate_of"
    RELATED_TO = "related_to"
    DERIVED_FROM = "derived_from"
    ASSIGNED_TO = "assigned_to"


WORK_ITEM_TYPES: tuple[str, ...] = tuple(WorkType)
WORK_ITEM_STATUSES: tuple[str, ...] = tuple(WorkItemStatus)
LINK_TYPES: tuple[str, ...] = tuple(LinkType)


class WorkItem(IdMixin, TimestampMixin, VersionMixin, Base):
    __tablename__ = "work_item"

    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_item.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    org_unit_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL"), nullable=True, index=True
    )
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    baseline_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    forecast_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    priority_tier: Mapped[int | None] = mapped_column(nullable=True)
    completed_percent: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)
    hse_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivery_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="native", nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "type IN (" + ",".join(f"'{item}'" for item in WORK_ITEM_TYPES) + ")",
            name="work_item_type",
        ),
        CheckConstraint(
            "status IN (" + ",".join(f"'{item}'" for item in WORK_ITEM_STATUSES) + ")",
            name="work_item_status",
        ),
        CheckConstraint("origin IN ('native','external','ai_extracted')", name="work_item_origin"),
    )


class WorkLink(IdMixin, TimestampMixin, Base):
    __tablename__ = "work_link"

    src_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dst_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=1, nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="human", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("src_id", "dst_id", "link_type", name="uq_work_link_edge"),
        CheckConstraint(
            "link_type IN (" + ",".join(f"'{item}'" for item in LINK_TYPES) + ")",
            name="work_link_type",
        ),
        CheckConstraint("status IN ('proposed','active','rejected')", name="work_link_status"),
        CheckConstraint("origin IN ('human','system','ai')", name="work_link_origin"),
    )


class LinkTypeRule(IdMixin, TimestampMixin, Base):
    """Whitelist of valid (src_type, dst_type, link_type) combinations (plan §7.2)."""

    __tablename__ = "link_type_rule"

    src_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    dst_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    link_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("src_type", "dst_type", "link_type", name="uq_link_type_rule_combo"),
    )


class Allocation(IdMixin, Base):
    """Planned hours per resource per window (plan §7.3)."""

    __tablename__ = "allocation"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours_total: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    hours_per_week: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scenario_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('project','operational','bau','leave')", name="ck_allocation_kind"
        ),
    )


class BenefitMeasurement(IdMixin, TimestampMixin, Base):
    __tablename__ = "benefit_measurement"

    benefit_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)
    baseline: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    target: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    actual: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    forecast: Mapped[Decimal | None] = mapped_column(Numeric(18, 3), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("benefit_id", "period", name="uq_benefit_measurement_period"),
    )
