"""Phase 5 — Scoring & prioritisation: scoring_model, scores, overrides; work_item.completed_percent.

Revision ID: 0005_phase5_scoring
Revises: 0004_phase4_ai_work_intelligence
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase5_scoring"
down_revision: str | None = "0004_phase4_ai_work_intelligence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scoring_model",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("gating_floor_tier", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scoring_model")),
    )
    op.create_index(op.f("ix_scoring_model_name"), "scoring_model", ["name"])

    op.create_table(
        "scoring_model_criterion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("criterion", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.Numeric(precision=5, scale=3), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("anchored_scale", sa.JSON(), nullable=False),
        sa.Column("gating", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["scoring_model.id"], name=op.f("fk_scoring_model_criterion_model_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scoring_model_criterion")),
    )
    op.create_index(op.f("ix_scoring_model_criterion_model_id"), "scoring_model_criterion", ["model_id"])

    op.create_table(
        "score",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=3), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_item.id"], name=op.f("fk_score_work_item_id")),
        sa.ForeignKeyConstraint(["model_id"], ["scoring_model.id"], name=op.f("fk_score_model_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score")),
    )
    op.create_index(op.f("ix_score_work_item_id"), "score", ["work_item_id"], unique=True)
    op.create_index(op.f("ix_score_model_id"), "score", ["model_id"])

    op.create_table(
        "score_override",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("score_id", sa.Uuid(), nullable=False),
        sa.Column("tier", sa.Integer(), nullable=False),
        sa.Column("original_tier", sa.Integer(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["score_id"], ["score.id"], name=op.f("fk_score_override_score_id")),
        sa.ForeignKeyConstraint(["approver_id"], ["app_user.id"], name=op.f("fk_score_override_approver_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_score_override")),
    )
    op.create_index(op.f("ix_score_override_score_id"), "score_override", ["score_id"])

    with op.batch_alter_table("work_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("completed_percent", sa.Numeric(precision=4, scale=1), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("work_item", schema=None) as batch_op:
        batch_op.drop_column("completed_percent")
    op.drop_index(op.f("ix_score_override_score_id"), table_name="score_override")
    op.drop_table("score_override")
    op.drop_index(op.f("ix_score_model_id"), table_name="score")
    op.drop_index(op.f("ix_score_work_item_id"), table_name="score")
    op.drop_table("score")
    op.drop_index(op.f("ix_scoring_model_criterion_model_id"), table_name="scoring_model_criterion")
    op.drop_table("scoring_model_criterion")
    op.drop_index(op.f("ix_scoring_model_name"), table_name="scoring_model")
    op.drop_table("scoring_model")
