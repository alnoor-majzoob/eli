"""Repair Phase 1 seed rows that used non-UUID primary keys.

Revision ID: 0010_fix_seed_uuids
Revises: 0009_drop_score_version
Create Date: 2026-11-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_fix_seed_uuids"
down_revision: str | None = "0009_drop_score_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOD_IDS = {
    "sod-SOD-1": "d4b4990a7bac51bf8fca59d833cb98c2",
    "sod-SOD-2": "6c5fb2b58dc4556d991abc668dfbb44a",
    "sod-SOD-3": "c9bdd2c90c0454638d8cc83b3d1886e1",
    "sod-SOD-4": "0b146563f9da5940904971a3c6c892a2",
    "sod-SOD-5": "5859bda6a4095e43bbf95f3c5f73a168",
    "sod-SOD-6": "2b126fdc70fd564badf627151534f577",
}

_WORKFLOW_IDS = {
    "wf-demand_approval": "f8d161b83f4254beb60b8693700010e4",
    "wf-stage_gate": "09658fbe2a4d51adb22b72f2012b87c0",
}


def _update_id(table: str, old: str, new: str) -> None:
    op.execute(
        sa.text(f"UPDATE {table} SET id = :new WHERE id = :old").bindparams(
            new=new, old=old
        )
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return

    for old, new in _SOD_IDS.items():
        _update_id("sod_rule", old, new)

    for old, new in _WORKFLOW_IDS.items():
        _update_id("workflow_def", old, new)
        op.execute(
            sa.text(
                "UPDATE workflow_instance SET definition_id = :new "
                "WHERE definition_id = :old"
            ).bindparams(new=new, old=old)
        )


def downgrade() -> None:
    pass
