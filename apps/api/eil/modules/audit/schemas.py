"""Audit schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditRead(BaseModel):
    seq: int
    ts: datetime
    actor_id: str | None
    actor_type: str
    action: str
    entity_type: str | None
    entity_id: UUID | None
    org_unit_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    request_id: str | None
    reason: str | None
    prev_hash: str | None
    hash: str | None


class ChainVerificationResponse(BaseModel):
    rows: int
    broken_at: str | None
    ok: bool
