"""Governance API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    instance_id: UUID
    work_item_id: UUID
    step: int
    approver_role: str
    status: str
    requested_by: UUID
    decided_by: UUID | None
    decided_at: datetime | None
    comment: str | None
    decision_reason: str | None
    due_at: datetime | None
    escalated_at: datetime | None
    delegated_to: UUID | None
    delegated_by: UUID | None
    delegated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalPage(BaseModel):
    items: list[ApprovalRead]
    total: int


class WorkflowDefRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key: str
    name: str
    version: int
    active: bool
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WorkflowInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    definition_id: UUID
    work_item_id: UUID
    step: int
    current_state: str
    status: str
    requested_by: UUID
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DecideApprovalRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = None


class DelegateApprovalRequest(BaseModel):
    delegate_to: UUID
