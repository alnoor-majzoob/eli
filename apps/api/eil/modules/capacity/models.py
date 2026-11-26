"""Capacity & resource model (plan §7.1, Phase 6, T6.1)."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin

PROFICIENCY_MIN = 1
PROFICIENCY_MAX = 5


class Competency(IdMixin, TimestampMixin, Base):
    __tablename__ = "competency"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ResourceSkill(IdMixin, TimestampMixin, Base):
    """Resource competencies — proficiency levels used for assignment eligibility."""

    __tablename__ = "resource_skill"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competency_id: Mapped[UUID] = mapped_column(
        ForeignKey("competency.id", ondelete="CASCADE"), nullable=False
    )
    proficiency: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "resource_id", "competency_id", name="uq_resource_skill_resource_competency"
        ),
        CheckConstraint(
            f"proficiency BETWEEN {PROFICIENCY_MIN} AND {PROFICIENCY_MAX}",
            name="ck_resource_skill_proficiency",
        ),
    )


class Certification(IdMixin, TimestampMixin, Base):
    """Certifications with expiry (plan §7.1)."""

    __tablename__ = "certification"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competency_id: Mapped[UUID] = mapped_column(
        ForeignKey("competency.id", ondelete="CASCADE"), nullable=False
    )
    certificate_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issued_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'revoked')", name="ck_certification_status"
        ),
    )


class ResourceCalendar(IdMixin, TimestampMixin, Base):
    """Weekday shift availability, shift and location attributes (plan §9.2, §7.1)."""

    __tablename__ = "resource_calendar"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    monday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tuesday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wednesday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    thursday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    friday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saturday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sunday: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_hours: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("8"), nullable=False
    )
    shift: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ResourceLeave(IdMixin, TimestampMixin, Base):
    """Leave (from hr-sim) as allocation absence (plan §9.2)."""

    __tablename__ = "resource_leave"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    leave_type: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "leave_type IN ('annual','sick','maternity','personal','other')",
            name="ck_resource_leave_type",
        ),
    )


class ResourceContract(IdMixin, TimestampMixin, Base):
    """Contracted weekly hours per resource window (plan §9.2)."""

    __tablename__ = "resource_contract"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours_per_week: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active','terminated')", name="ck_resource_contract_status"),
    )


class BauBaseline(IdMixin, TimestampMixin, Base):
    """BAU baseline % of contracted hours per resource (plan §9.2)."""

    __tablename__ = "bau_baseline"

    resource_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    bau_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    __table_args__ = (
        CheckConstraint("bau_percent BETWEEN 0 AND 100", name="ck_bau_baseline_percent"),
    )


class Scenario(IdMixin, TimestampMixin, Base):
    """What-if scenario overlay (plan §7.1, §9.4).

    The baseline is never copied or mutated; engines read through
    ``ScenarioChange`` rows via their ``scenario_id``.
    """

    __tablename__ = "scenario"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=False, index=True
    )
    promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ScenarioChange(IdMixin, TimestampMixin, Base):
    """Overlay rows applied over the baseline (plan §9.4): allocation edits
    (``allocation_id`` set), new scenario allocations (``allocation_id`` NULL)
    and priority changes (``work_item_id`` set)."""

    __tablename__ = "scenario_change"

    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allocation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("allocation.id", ondelete="SET NULL"), nullable=True, index=True
    )
    work_item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=True, index=True
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
