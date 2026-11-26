"""Integration module models: external refs, approved sources, sync runs, conflicts."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eil.core.db import Base
from eil.core.models import IdMixin, TimestampMixin, utcnow

SYSTEMS: tuple[str, ...] = ("p6", "eam", "erp", "hr", "m365")
KINDS: tuple[str, ...] = (
    "project",
    "activity",
    "milestone",
    "work_order",
    "person",
    "certification",
    "meeting",
    "message",
    "document",
)


class ExternalRef(IdMixin, TimestampMixin, Base):
    """Binding between a work item and a record in a system of record (plan §7.3)."""

    __tablename__ = "external_ref"

    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    system: Mapped[str] = mapped_column(String(30), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owned_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("system", "external_id", name="uq_external_ref_binding"),)


class ApprovedSource(IdMixin, TimestampMixin, Base):
    """Approved system-of-record source (plan §7.3; SoD-4 per plan §13.2, T3.5)."""

    __tablename__ = "approved_source"

    type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_filters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    classification: Mapped[str] = mapped_column(String(30), default="internal", nullable=False)
    retention_days: Mapped[int | None] = mapped_column(nullable=True)
    ai_processing_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owned_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    write_back_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    write_back_fields: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    write_back_requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    sync_cursor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sync_lag_seconds: Mapped[int | None] = mapped_column(nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )


class SourceArtifact(IdMixin, TimestampMixin, Base):
    """Raw ingested record (plan §7.3); the canonical payload is stored as JSON."""

    __tablename__ = "source_artifact"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("approved_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(30), default="internal", nullable=False)
    ai_processing_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_artifact_binding"),
    )


class SyncRun(IdMixin, TimestampMixin, Base):
    """One sync execution for a source (plan §10 Phase 3, T3.6 'sync-run log')."""

    __tablename__ = "sync_run"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("approved_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    records_count: Mapped[int] = mapped_column(nullable=True)
    errors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    triggered_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SyncConflict(IdMixin, TimestampMixin, Base):
    """Reconciliation conflict: external change hit a non-owned field (plan §10, T3.6)."""

    __tablename__ = "sync_conflict"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("approved_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    external_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    local_value: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WriteBackChange(IdMixin, TimestampMixin, Base):
    """A gated write-back change awaiting approval (plan §10, T3.5 + T3.7)."""

    __tablename__ = "write_back_change"

    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("approved_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("work_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    approved_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
