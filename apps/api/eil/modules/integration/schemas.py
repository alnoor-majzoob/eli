"""Integration API schemas (plan §10, Phase 3, T3.5/T3.6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApprovedSourceCreate(BaseModel):
    type: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    scope_filters: dict[str, Any] = Field(default_factory=dict)
    owner: str = Field(min_length=1, max_length=200)
    classification: str = Field(default="internal", max_length=30)
    retention_days: int | None = None
    ai_processing_allowed: bool = False
    owned_fields: list[str] = Field(default_factory=list)
    write_back_enabled: bool = False
    write_back_fields: list[str] = Field(default_factory=list)
    write_back_requires_approval: bool = False


class ApprovedSourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    scope_filters: dict[str, Any] | None = None
    owner: str | None = None
    classification: str | None = None
    retention_days: int | None = None
    ai_processing_allowed: bool | None = None
    enabled: bool | None = None
    owned_fields: list[str] | None = None
    write_back_enabled: bool | None = None
    write_back_fields: list[str] | None = None
    write_back_requires_approval: bool | None = None
    # Two-person rule (SOD-4): distinct approver for protected changes.
    approved_by: str | None = None
    reason: str | None = None


class ApprovedSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    name: str
    description: str | None
    scope_filters: dict[str, Any]
    owner: str
    classification: str
    retention_days: int | None
    ai_processing_allowed: bool
    enabled: bool
    owned_fields: list[str]
    write_back_enabled: bool
    write_back_fields: list[str]
    write_back_requires_approval: bool
    sync_cursor: str | None
    sync_lag_seconds: int | None
    last_sync_at: datetime | None
    last_sync_error: str | None
    created_by: UUID | None
    created_at: datetime


class ApprovedSourceStatusRead(BaseModel):
    """Connector health + sync status for the admin UI (T3.6 'health and lag')."""

    source_id: UUID
    health: str
    last_sync_at: datetime | None
    lag_seconds: int | None
    error_count: int
    conflicts_unresolved: int


class ConnectorCapabilityRead(BaseModel):
    system: str
    record_types: list[str]
    modes: list[str]
    default_mode: str
    push_supported: bool


class ConnectorRead(BaseModel):
    system: str
    capabilities: ConnectorCapabilityRead
    mode: str
    push_supported: bool


class WebhookRead(BaseModel):
    system: str
    accepted: int


class SyncConflictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    work_item_id: UUID
    field: str
    external_value: dict[str, Any] | None
    local_value: dict[str, Any] | None
    description: str | None
    resolved: bool
    resolved_at: datetime | None
    created_at: datetime


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    status: str
    records_count: int | None
    errors: list[str]
    started_at: datetime
    finished_at: datetime | None
    triggered_by: str | None
    last_error: str | None
    created_at: datetime


class WriteBackChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    work_item_id: UUID
    action: str
    payload: dict[str, Any]
    status: str
    approved_by: UUID | None
    executed_at: datetime | None
    rejected_reason: str | None
    created_at: datetime


class WriteBackChangeSubmit(BaseModel):
    """Enqueue a gated write-back change (plan §10, Phase 3, T3.7)."""

    action: str = Field(min_length=1, max_length=50)
    work_item_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
