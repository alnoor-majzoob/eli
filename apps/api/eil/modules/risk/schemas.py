"""Risk & escalation API schemas (plan §10, Phase 7, T7.8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RiskRadarRow(BaseModel):
    """Portfolio risk row: confidence x impact (plan §9.5)."""

    model_config = ConfigDict(from_attributes=True)

    item_id: UUID
    title: str
    type: str
    status: str
    confidence: float | None
    impact: float
    risk_score: float


class EscalationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_item_id: UUID | None
    competency_id: UUID | None
    root_cause: str
    impact_cascade: str | None
    recommended_actions: list[dict[str, Any]]
    required_decision: str | None
    target_role: str
    due_at: datetime
    sla_days: int
    status: str
    acknowledged_by: UUID | None
    acknowledged_at: datetime | None
    created_at: datetime


class EscalationAckRead(BaseModel):
    id: UUID
    status: str
    acknowledged_by: UUID | None
    acknowledged_at: datetime | None
