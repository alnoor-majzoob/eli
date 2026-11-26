"""Prioritisation schemas (plan §10, Phase 5, T5.3)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from eil.modules.execution.models import WorkType


class PrioritizedItemRead(BaseModel):
    """Prioritisation board row: tier + calculated score + rationale + cut-line."""

    id: UUID
    type: WorkType
    title: str
    tier: int
    score: float
    rationale: dict[str, Any] | None
    model_id: UUID
    computed_at: datetime
    in_cut_line: bool


class AllocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    resource_id: UUID
    work_item_id: UUID | None
    kind: str
    start_date: date
    end_date: date
    hours_total: float | None
    hours_per_week: float | None
    locked: bool
    scenario_id: UUID | None


class AllocationCreate(BaseModel):
    resource_id: UUID
    work_item_id: UUID | None = None
    kind: str
    start_date: date
    end_date: date
    hours_total: Decimal | None = None
    hours_per_week: Decimal | None = None
    locked: bool = False


class AllocationUpdate(BaseModel):
    kind: str | None = None
    work_item_id: UUID | None = None
    start_date: date | None = None
    end_date: date | None = None
    hours_total: Decimal | None = None
    hours_per_week: Decimal | None = None
    locked: bool | None = None


class OverrideCreate(BaseModel):
    """Priority override request (plan §10, Phase 5, T5.3).

    ``tier`` must differ from the calculated tier in spirit — the override is
    recorded with ``original_tier`` preserved; SoD-2 (the approver must differ
    from the requester) is enforced in the router.
    """

    tier: int = Field(ge=1, le=4)
    justification: str = Field(min_length=1, max_length=500)
    approver_id: UUID


class ScoreOverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    score_id: UUID
    tier: int
    original_tier: int
    justification: str
    approver_id: UUID | None
    approved_at: datetime
