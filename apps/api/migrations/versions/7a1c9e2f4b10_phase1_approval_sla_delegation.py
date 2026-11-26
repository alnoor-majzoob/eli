"""Phase 1: approval SLA, escalation and delegation fields.

Revision ID: 7a1c9e2f4b10
Revises: dcdbe4b6cefe
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7a1c9e2f4b10"
down_revision: str | None = "dcdbe4b6cefe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("approval", schema=None) as batch_op:
        batch_op.add_column(sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column("delegated_to", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("delegated_by", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(sa.Column("delegated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_approval_delegated_to_app_user"),
            "app_user",
            ["delegated_to"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_approval_delegated_by_app_user"),
            "app_user",
            ["delegated_by"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(batch_op.f("ix_approval_due_at"), ["due_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("approval", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_approval_due_at"))
        batch_op.drop_constraint(batch_op.f("fk_approval_delegated_by_app_user"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_approval_delegated_to_app_user"), type_="foreignkey")
        batch_op.drop_column("delegated_at")
        batch_op.drop_column("delegated_by")
        batch_op.drop_column("delegated_to")
        batch_op.drop_column("escalated_at")
        batch_op.drop_column("due_at")
