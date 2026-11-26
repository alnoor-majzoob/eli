"""Phase 9 — drop the stray ``score.version`` column (user-test finding).

The Phase 5 migration created a ``version`` column on ``score``; the model
``eil.modules.prioritization.models.Score`` never had such a field (the query
path never selected it). Removes the remaining drift reported by the
user-level drift audit (``apps/api/tests/test_migration_drift.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_drop_score_version"
down_revision: str | None = "0008_add_missing_timestamp_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("score", schema=None) as batch_op:
        batch_op.drop_column("version")


def downgrade() -> None:
    with op.batch_alter_table("score", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )
