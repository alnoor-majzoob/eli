"""Capacity & what-if API schemas (plan §10, Phase 6, T6.7)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HeatmapWeekRead(BaseModel):
    week_start: date
    available: Decimal
    demand: Decimal
    utilisation: Decimal | None
    status: str | None


class HeatmapResourceRead(BaseModel):
    resource_id: UUID
    resource_name: str
    weeks: list[HeatmapWeekRead]


class CapacityHeatmapRead(BaseModel):
    resources: list[HeatmapResourceRead]


class ConflictAffectedRead(BaseModel):
    id: UUID
    type: str
    title: str
    depth: int
    criticality: Decimal


class CapacityConflictRead(BaseModel):
    resource_id: UUID
    week_start: date
    utilisation: Decimal
    status: str
    affected: list[ConflictAffectedRead]


class OptimiserAllocationRead(BaseModel):
    task_id: UUID
    resource_id: UUID
    week_start: date
    hours: int


class OptimiserDeltasRead(BaseModel):
    unmet_hours: Decimal
    overload_hours: Decimal
    reassignment_hours: Decimal
    skill_gap_hours: Decimal
    delayed_commitments: int


class OptimiserOptionRead(BaseModel):
    strategy: str
    option_index: int
    allocations: list[OptimiserAllocationRead]
    deltas: OptimiserDeltasRead


class ScenarioChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_id: UUID
    allocation_id: UUID | None
    work_item_id: UUID | None
    payload: dict[str, Any]
    reason: str | None
    created_at: datetime


class ScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    author_id: UUID
    promoted: bool
    approved_by_id: UUID | None
    promoted_at: datetime | None
    expires_at: date | None
    expired: bool
    created_at: datetime


class ScenarioCreate(BaseModel):
    name: str
    description: str | None = None
    expires_at: date | None = None


class ScenarioChangeCreate(BaseModel):
    allocation_id: UUID | None = None
    work_item_id: UUID | None = None
    payload: dict[str, Any]
    reason: str | None = None


class ScenarioPromoteRequest(BaseModel):
    approver_id: UUID


class ScenarioMetricsRead(BaseModel):
    scenario_id: UUID
    overload_hours: Decimal
    red_weeks: int
    delayed_commitments: int
    cost_proxy: Decimal
