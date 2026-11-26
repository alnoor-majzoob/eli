"""AI schemas (plan §7.3, Phase 4, plan §8.5/§8.6/§8.7).

Two groups:
- Suggestion inbox schemas: ``AiSuggestionRead`` and accept/reject/bulk bodies.
- Prompt output schemas: one Pydantic model per prompt (T4.2-T4.8).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# --- Suggestion inbox (T4.9) ---


class AiSuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    payload: dict[str, Any]
    evidence: dict[str, Any] | None
    confidence: Decimal | None
    model: str
    prompt_version: str
    llm_call_id: UUID | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_reason: str | None
    resulting_entity: UUID | None
    created_at: datetime


class AiSuggestionAcceptBody(BaseModel):
    """Edit-and-accept: apply optional payload edits, then accept."""

    payload: dict[str, Any] | None = None
    reason: str | None = None


class AiSuggestionRejectBody(BaseModel):
    reason: str = Field(min_length=1)


class AiSuggestionBulkItem(BaseModel):
    suggestion_id: UUID
    action: Literal["accept", "reject"]
    reason: str | None = None


class AiSuggestionBulkBody(BaseModel):
    items: list[AiSuggestionBulkItem] = Field(min_length=1)


class AiSuggestionBulkResult(BaseModel):
    accepted: list[UUID]
    rejected: list[UUID]
    errors: dict[str, str]


# --- Prompt outputs (T4.2-T4.8) ---


class CandidateOutput(BaseModel):
    title: str
    kind: Literal["task", "commitment", "decision", "milestone"]
    summary: str
    evidence_quote: str
    speaker: str | None = None
    confidence: float | None = None
    owner_hint: str | None = None
    due_phrase: str | None = None


class DetectCandidatesOutput(BaseModel):
    candidates: list[CandidateOutput]


class StructuredItem(BaseModel):
    title: str
    summary: str
    kind: Literal["task", "commitment", "decision", "milestone"]
    evidence_quote: str
    speaker: str | None = None
    confidence: float | None = None
    priority: int | None = None
    owner_hint: str | None = None
    due_phrase: str | None = None
    duplicate_of_index: int | None = None


class StructuredItemsOutput(BaseModel):
    items: list[StructuredItem]


class OwnerCandidate(BaseModel):
    user_id: str
    name: str
    reason: str
    score: float


class OwnerSuggestionOutput(BaseModel):
    candidates: list[OwnerCandidate]


class ClassificationOutput(BaseModel):
    type: str
    category: str
    department: str
    hse_critical: bool
    regulatory: bool
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class ClassifyItemOutput(BaseModel):
    items: list[ClassificationOutput]


class AdjudicateDuplicateOutput(BaseModel):
    verdict: Literal["duplicate", "related", "distinct"]
    reason: str | None = None


class RerankedLink(BaseModel):
    entity_id: str
    link_type: Literal["aligns_to", "part_of"]
    rationale: str
    confidence: float | None = None


class RerankLinksOutput(BaseModel):
    links: list[RerankedLink]


class ScoreAssistScore(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str | None = None


class ScoreAssistOutput(BaseModel):
    scores: dict[str, ScoreAssistScore] = Field(default_factory=dict)
    explanation: str | None = None


class AiSuggestionDetail(BaseModel):
    """Inbox detail: source excerpt + highlighted evidence (plan §8.6 provenance)."""

    id: str
    kind: str
    status: str
    payload: dict
    evidence: dict | None
    confidence: float | None
    model: str
    prompt_version: str
    source_artifact_id: str | None
    source_excerpt: str | None
    reviewer_name: str | None
    reviewed_at: datetime | None
    created_at: datetime
