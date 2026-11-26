"""Phase 2 — Enterprise Work Graph: link_type_rule and allocation tables.

Revision ID: 0002_phase2_work_graph
Revises: 7a1c9e2f4b10
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_work_graph"
down_revision: str | None = "7a1c9e2f4b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ALL_TYPES = (
    "objective",
    "key_result",
    "initiative",
    "demand",
    "program",
    "project",
    "milestone",
    "task",
    "commitment",
    "risk",
    "issue",
    "benefit",
    "decision",
)

LINK_TYPES = (
    "part_of",
    "aligns_to",
    "depends_on",
    "fulfils",
    "realizes",
    "threatens",
    "mitigates",
    "duplicate_of",
    "related_to",
    "derived_from",
    "assigned_to",
)

# Allowed (src_type, dst_type) per link type — mirrors the service-layer rules in
# eil.modules.execution.service (_LINK_DST_TYPES / _LINK_SRC_TYPES).
_DST_ALLOWED = {
    "part_of": set(ALL_TYPES) - {"objective"},
    "aligns_to": {"objective", "key_result"},
    "fulfils": {"commitment"},
    "realizes": {"benefit"},
    "mitigates": {"risk", "issue"},
    "threatens": set(ALL_TYPES),
    "depends_on": set(ALL_TYPES),
    "duplicate_of": set(ALL_TYPES),
    "related_to": set(ALL_TYPES),
    "derived_from": set(ALL_TYPES),
    "assigned_to": set(ALL_TYPES),
}

_SRC_ALLOWED = {
    "aligns_to": {"initiative", "demand", "task", "project", "commitment"},
    "fulfils": {"task", "commitment", "project"},
    "realizes": {"project", "initiative", "program"},
    "mitigates": {"task", "project", "program"},
    "threatens": {"risk", "issue"},
    "derived_from": set(ALL_TYPES),
}


def _rule_combos() -> list[dict[str, str]]:
    combos: set[tuple[str, str, str]] = set()
    for link_type in LINK_TYPES:
        srcs = _SRC_ALLOWED.get(link_type, set(ALL_TYPES))
        dsts = _DST_ALLOWED[link_type]
        for src_type in srcs:
            for dst_type in dsts:
                combos.add((src_type, dst_type, link_type))
    rows = [
        {"id": uuid4(), "src_type": src, "dst_type": dst, "link_type": link}
        for src, dst, link in sorted(combos)
    ]
    return rows


def upgrade() -> None:
    op.create_table(
        "link_type_rule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("src_type", sa.String(length=30), nullable=False),
        sa.Column("dst_type", sa.String(length=30), nullable=False),
        sa.Column("link_type", sa.String(length=40), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_link_type_rule")),
        sa.UniqueConstraint(
            "src_type", "dst_type", "link_type", name=op.f("uq_link_type_rule_combo")
        ),
    )
    op.create_index(op.f("ix_link_type_rule_src_type"), "link_type_rule", ["src_type"])
    op.create_index(op.f("ix_link_type_rule_dst_type"), "link_type_rule", ["dst_type"])
    op.create_index(op.f("ix_link_type_rule_link_type"), "link_type_rule", ["link_type"])

    link_type_rule = sa.table(
        "link_type_rule",
        sa.column("id", sa.Uuid()),
        sa.column("src_type", sa.String(length=30)),
        sa.column("dst_type", sa.String(length=30)),
        sa.column("link_type", sa.String(length=40)),
    )
    op.get_bind().execute(link_type_rule.insert(), _rule_combos())

    op.create_table(
        "allocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("hours_total", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("hours_per_week", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_allocation")),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["app_user.id"], name=op.f("fk_allocation_resource_id")
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["work_item.id"], name=op.f("fk_allocation_work_item_id")
        ),
        sa.CheckConstraint(
            "kind IN ('project','operational','bau','leave')", name="ck_allocation_kind"
        ),
    )
    op.create_index(op.f("ix_allocation_resource_id"), "allocation", ["resource_id"])
    op.create_index(op.f("ix_allocation_work_item_id"), "allocation", ["work_item_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_allocation_work_item_id"), table_name="allocation")
    op.drop_index(op.f("ix_allocation_resource_id"), table_name="allocation")
    op.drop_table("allocation")
    op.drop_index(op.f("ix_link_type_rule_link_type"), table_name="link_type_rule")
    op.drop_index(op.f("ix_link_type_rule_dst_type"), table_name="link_type_rule")
    op.drop_index(op.f("ix_link_type_rule_src_type"), table_name="link_type_rule")
    op.drop_table("link_type_rule")
