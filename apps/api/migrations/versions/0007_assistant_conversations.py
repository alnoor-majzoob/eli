"""Phase 8 — assistant_conversation table (T8.3 conversation logging).

Revision ID: 0007_assistant_conversations
Revises: 0006_phase6_phase7_capacity_risk
Create Date: 2026-11-22

Creates the ``assistant_conversation`` table for persisting Ask-EIL
conversations (T8.3 conversation logging).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_assistant_conversations"
down_revision: str | None = "0006_phase6_phase7_capacity_risk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assistant_conversation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("principal", sa.String(200), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_assistant_conversation_principal",
        "assistant_conversation",
        ["principal"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_conversation_principal", table_name="assistant_conversation"
    )
    op.drop_table("assistant_conversation")
