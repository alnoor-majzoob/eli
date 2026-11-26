"""Append-only audit logging with hash-chained tamper evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.models import utcnow
from eil.modules.audit.models import AuditLog


@dataclass(frozen=True)
class ChainVerification:
    rows: int
    broken_at: str | None = None

    @property
    def ok(self) -> bool:
        return self.broken_at is None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _timestamp_token(ts: datetime) -> str:
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    return ts.isoformat(timespec="microseconds")


def _chain_hash(
    *,
    ts: datetime,
    prev_hash: bytes | None,
    row: Mapping[str, Any],
) -> bytes:
    payload = {key: row[key] for key in sorted(row)}
    payload["prev_hash"] = prev_hash.hex() if prev_hash is not None else None
    digest = hashlib.sha256(prev_hash or b"")
    digest.update(_canonical({"ts": _timestamp_token(ts), "row": payload}).encode("utf-8"))
    return digest.digest()


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: str | None,
    actor_type: str = "user",
    action: str,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    org_unit_id: UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
    reason: str | None = None,
) -> AuditLog:
    result = await session.execute(
        select(AuditLog.seq, AuditLog.hash).order_by(AuditLog.seq.desc()).limit(1)
    )
    row = result.one_or_none()
    prev_hash = bytes(row[1]) if row and row[1] else None
    ts = utcnow()

    row_data: dict[str, Any] = {
        "actor_id": actor_id,
        "actor_type": actor_type,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id else None,
        "org_unit_id": str(org_unit_id) if org_unit_id else None,
        "before": before,
        "after": after,
        "request_id": request_id,
        "reason": reason,
    }
    audit = AuditLog(
        ts=ts,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        org_unit_id=org_unit_id,
        before=before,
        after=after,
        request_id=request_id,
        reason=reason,
        prev_hash=prev_hash,
        hash=_chain_hash(ts=ts, prev_hash=prev_hash, row=row_data),
    )
    session.add(audit)
    await session.flush()
    return audit


def serialize_audit(row: AuditLog) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "ts": row.ts.isoformat() if isinstance(row.ts, datetime) else str(row.ts),
        "actor_id": row.actor_id,
        "actor_type": row.actor_type,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "org_unit_id": row.org_unit_id,
        "before": row.before,
        "after": row.after,
        "request_id": row.request_id,
        "reason": row.reason,
        "prev_hash": row.prev_hash.hex() if row.prev_hash else None,
        "hash": row.hash.hex() if row.hash else None,
    }


async def query_audit(
    session: AsyncSession,
    *,
    actor_id: str | None = None,
    actor_type: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    org_unit_id: UUID | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[AuditLog]:
    stmt = select(AuditLog)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if actor_type is not None:
        stmt = stmt.where(AuditLog.actor_type == actor_type)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if org_unit_id is not None:
        stmt = stmt.where(AuditLog.org_unit_id == org_unit_id)
    if from_ts is not None:
        stmt = stmt.where(AuditLog.ts >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AuditLog.ts <= to_ts)
    result = await session.execute(stmt.order_by(AuditLog.seq.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


async def verify_chain(session: AsyncSession) -> ChainVerification:
    rows = (await session.execute(select(AuditLog).order_by(AuditLog.seq))).scalars().all()
    prev_hash: bytes | None = None
    for row in rows:
        expected = _chain_hash(
            ts=row.ts,
            prev_hash=prev_hash,
            row={
                "actor_id": row.actor_id,
                "actor_type": row.actor_type,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "org_unit_id": str(row.org_unit_id) if row.org_unit_id else None,
                "before": row.before,
                "after": row.after,
                "request_id": row.request_id,
                "reason": row.reason,
            },
        )
        if not row.hash or bytes(row.hash) != expected:
            return ChainVerification(rows=row.seq, broken_at=row.action)
        prev_hash = bytes(row.hash)
    return ChainVerification(rows=len(rows), broken_at=None)


async def export_audit_csv(session: AsyncSession, *, limit: int = 10_000) -> list[dict[str, Any]]:
    rows = (
        (await session.execute(select(AuditLog).order_by(AuditLog.seq.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [serialize_audit(row) for row in rows]
