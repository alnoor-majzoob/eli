"""Phase 4 — AI Work Intelligence: llm_call telemetry + ai_suggestion table.

Tables follow plan §7.3 (authoritative DDL). ``llm_call.status``:
``ok | retried | repaired | failed | replayed``. ``ai_suggestion.kind``:
``extracted_item | link | duplicate | priority_scores | owner | mitigation``.

Revision ID: 0004_phase4_ai_work_intelligence
Revises: 0003_phase3_integration
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase4_ai_work_intelligence"
down_revision: str | None = "0003_phase3_integration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_call",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=50), nullable=False),
        sa.Column("model_alias", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("redaction_applied", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call")),
    )
    op.create_index(op.f("ix_llm_call_created_at"), "llm_call", ["created_at"])
    op.create_index(op.f("ix_llm_call_request_hash"), "llm_call", ["request_hash"])

    op.create_table(
        "ai_suggestion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("llm_call_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("resulting_entity", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["llm_call_id"], ["llm_call.id"], name=op.f("fk_ai_suggestion_llm_call_id")),
        sa.ForeignKeyConstraint(["resulting_entity"], ["work_item.id"], name=op.f("fk_ai_suggestion_resulting_entity")),
        sa.ForeignKeyConstraint(["reviewed_by"], ["app_user.id"], name=op.f("fk_ai_suggestion_reviewed_by")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_suggestion")),
    )
    op.create_index(op.f("ix_ai_suggestion_created_at"), "ai_suggestion", ["created_at"])
    op.create_index(op.f("ix_ai_suggestion_llm_call_id"), "ai_suggestion", ["llm_call_id"])
    op.create_index(op.f("ix_ai_suggestion_status"), "ai_suggestion", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_suggestion_status"), table_name="ai_suggestion")
    op.drop_index(op.f("ix_ai_suggestion_llm_call_id"), table_name="ai_suggestion")
    op.drop_index(op.f("ix_ai_suggestion_created_at"), table_name="ai_suggestion")
    op.drop_table("ai_suggestion")
    op.drop_index(op.f("ix_llm_call_request_hash"), table_name="llm_call")
    op.drop_index(op.f("ix_llm_call_created_at"), table_name="llm_call")
    op.drop_table("llm_call")
