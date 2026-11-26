"""Phase 9 — add missing timestamp columns to drifted tables (user-test finding).

Revision ID: 0008_add_missing_ts
Revises: 0007_assistant_conversations
Create Date: 2026-11-23

The ``TimestampMixin`` columns (``created_at``/``updated_at``) are missing on
``ai_suggestion``, ``score``, ``score_override``, ``scoring_model`` and
``scoring_model_criterion`` in migration-created databases (added by model
changes after 0005/0006). Alembic-managed databases crash on
``GET /api/v1/prioritization`` (``no such column: score.created_at``); the
app itself is unaffected because ``Base.metadata.create_all`` creates the
tables from the models. Re-verified with ``apps/api/tests/test_migration_drift.py``
(schemas in sync with models) — that test fails until this migration lands.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_add_missing_ts"
down_revision: str | None = "0007_assistant_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES_WITH_UPDATED_AT = (
    "ai_suggestion",
    "score",
    "score_override",
    "scoring_model",
    "scoring_model_criterion",
)


def upgrade() -> None:
    with op.batch_alter_table("score", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
        )
    for table in _TABLES_WITH_UPDATED_AT:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
            )


def downgrade() -> None:
    for table in _TABLES_WITH_UPDATED_AT:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column("updated_at")
    with op.batch_alter_table("score", schema=None) as batch_op:
        batch_op.drop_column("created_at")
