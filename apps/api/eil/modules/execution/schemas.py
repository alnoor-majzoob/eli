"""Core execution API schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from eil.modules.execution.models import LinkType, WorkItemStatus, WorkType


class WorkItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: WorkType
    title: str
    description: str | None
    status: WorkItemStatus
    parent_id: UUID | None
    owner_id: UUID | None
    org_unit_id: UUID | None
    planned_start: date | None
    planned_end: date | None
    baseline_end: date | None
    forecast_end: date | None
    priority_score: Decimal | None
    priority_tier: int | None
    hse_critical: bool
    delivery_confidence: Decimal | None
    completed_percent: Decimal | None
    origin: str
    attributes: dict[str, Any]
    created_by: UUID | None
    version: int
    created_at: datetime
    updated_at: datetime


class WorkItemPage(BaseModel):
    items: list[WorkItemRead]
    total: int
    limit: int
    offset: int


class WorkLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    src_id: UUID
    dst_id: UUID
    link_type: LinkType
    weight: Decimal
    origin: str
    status: str
    confidence: Decimal | None
    evidence: dict[str, Any] | None
    created_by: UUID | None
    created_at: datetime


class WorkLinkPage(BaseModel):
    items: list[WorkLinkRead]
    total: int


class BenefitMeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    benefit_id: UUID
    period: date
    baseline: Decimal | None
    target: Decimal | None
    actual: Decimal | None
    forecast: Decimal | None
    created_by: UUID | None
    created_at: datetime


class BenefitRealisationRead(BaseModel):
    benefit_id: UUID
    baseline: Decimal | None
    target: Decimal | None
    latest_actual: Decimal | None
    latest_forecast: Decimal | None
    realisation_pct: Decimal | None
    forecast_pct: Decimal | None
    as_of: date | None
    measurements: list[BenefitMeasurementRead]


class BenefitRollupRow(BaseModel):
    """Benefits → KRs → objectives roll-up row (plan Phase 5, T5.7)."""

    objective_id: UUID
    title: str
    kr_count: int
    benefit_count: int
    total_actual: Decimal | None
    total_target: Decimal | None
    total_forecast: Decimal | None
    latest_actual_at: date | None
    on_track: bool


class WorkItemBase(BaseModel):
    type: WorkType
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    owner_id: UUID | None = None
    org_unit_id: UUID | None = None
    parent_id: UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    baseline_end: date | None = None
    forecast_end: date | None = None
    priority_score: Decimal | None = None
    priority_tier: int | None = None
    hse_critical: bool = False
    delivery_confidence: Decimal | None = None
    origin: str = "native"
    attributes: dict[str, Any] = Field(default_factory=dict)


class WorkItemCreate(WorkItemBase):
    status: WorkItemStatus = WorkItemStatus.DRAFT


class WorkItemUpdate(BaseModel):
    type: WorkType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: WorkItemStatus | None = None
    owner_id: UUID | None = None
    org_unit_id: UUID | None = None
    parent_id: UUID | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    baseline_end: date | None = None
    forecast_end: date | None = None
    priority_score: Decimal | None = None
    priority_tier: int | None = None
    hse_critical: bool | None = None
    delivery_confidence: Decimal | None = None
    completed_percent: Decimal | None = None
    origin: str | None = None
    attributes: dict[str, Any] | None = None
    version: int | None = None


class WorkLinkCreate(BaseModel):
    src_id: UUID | None = None
    dst_id: UUID
    link_type: LinkType
    weight: Decimal = Decimal("1")
    origin: str = "human"
    status: str = "active"
    confidence: Decimal | None = None
    evidence: dict[str, Any] | None = None


class BenefitMeasurementCreate(BaseModel):
    period: date
    baseline: Decimal | None = None
    target: Decimal | None = None
    actual: Decimal | None = None
    forecast: Decimal | None = None


class BenefitMeasurementUpdate(BaseModel):
    baseline: Decimal | None = None
    target: Decimal | None = None
    actual: Decimal | None = None
    forecast: Decimal | None = None
