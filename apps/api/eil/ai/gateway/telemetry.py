"""``llm_call`` telemetry (plan §8.8)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.models import LlmCall
from eil.modules.integration.models import SourceArtifact


def hash_request(messages: list[dict[str, str]], model_id: str) -> str:
    """Deterministic request hash used as the idempotency/cache key."""
    payload = json.dumps([messages, model_id], sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def record_llm_call(
    session: AsyncSession,
    *,
    purpose: str,
    model_alias: str,
    model_id: str,
    prompt_version: str,
    request_hash: str,
    status: str,
    artifact_id: Any = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    redaction_applied: bool = True,
) -> LlmCall:
    call = LlmCall(
        purpose=purpose,
        model_alias=model_alias,
        model_id=model_id,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        status=status,
        request_hash=request_hash,
        redaction_applied=redaction_applied,
    )
    if artifact_id is None and session.in_transaction():
        # Best-effort: only bind artifacts already flushed in this session.
        artifact = (
            (
                await session.execute(
                    select(SourceArtifact.id).order_by(SourceArtifact.ingested_at.desc()).limit(1)
                )
            )
            .scalars()
            .first()
        )
        if artifact is not None:
            call.artifact_id = artifact
    session.add(call)
    await session.flush()
    return call
