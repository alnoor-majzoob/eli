"""Phase 6 & 7 — Capacity & risk/scenario tables missing from migrations.

Revision ID: 0006_phase6_phase7_capacity_risk
Revises: 0005_phase5_scoring
Create Date: 2026-11-22

The capacity (Phase 6) and risk/scenario (Phase 7) tables were only created by
``Base.metadata.create_all`` in tests; no migration created them, so every
alembic-managed database (local `make migrate`, e2e stack, production rollouts)
was missing them. This migration creates the missing tables per the current
models (single source of truth: ``eil.modules.capacity.models``,
``eil.modules.risk.models``, ``eil.modules.capacity.whatif``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase6_phase7_capacity_risk"
down_revision: str | None = "0005_phase5_scoring"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "competency",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=True),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competency")),
    )
    op.create_index(op.f("ix_competency_name"), "competency", ["name"])

    op.create_table(
        "resource_skill",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("competency_id", sa.Uuid(), nullable=False),
        sa.Column("proficiency", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["app_user.id"], name=op.f("fk_resource_skill_resource_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competency_id"], ["competency.id"], name=op.f("fk_resource_skill_competency_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_skill")),
        sa.UniqueConstraint("resource_id", "competency_id", name="uq_resource_skill_resource_competency"),
        sa.CheckConstraint("proficiency BETWEEN 1 AND 5", name="ck_resource_skill_proficiency"),
    )
    op.create_index(op.f("ix_resource_skill_resource_id"), "resource_skill", ["resource_id"])

    op.create_table(
        "certification",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("competency_id", sa.Uuid(), nullable=False),
        sa.Column("certificate_number", sa.String(length=100), nullable=True),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["app_user.id"], name=op.f("fk_certification_resource_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competency_id"], ["competency.id"], name=op.f("fk_certification_competency_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_certification")),
        sa.CheckConstraint("status IN ('active', 'expired', 'revoked')", name="ck_certification_status"),
    )
    op.create_index(op.f("ix_certification_resource_id"), "certification", ["resource_id"])

    op.create_table(
        "resource_calendar",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("monday", sa.Boolean(), nullable=False),
        sa.Column("tuesday", sa.Boolean(), nullable=False),
        sa.Column("wednesday", sa.Boolean(), nullable=False),
        sa.Column("thursday", sa.Boolean(), nullable=False),
        sa.Column("friday", sa.Boolean(), nullable=False),
        sa.Column("saturday", sa.Boolean(), nullable=False),
        sa.Column("sunday", sa.Boolean(), nullable=False),
        sa.Column("daily_hours", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("shift", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["app_user.id"], name=op.f("fk_resource_calendar_resource_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_calendar")),
    )

    op.create_table(
        "resource_leave",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("leave_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["app_user.id"], name=op.f("fk_resource_leave_resource_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_leave")),
        sa.CheckConstraint("leave_type IN ('annual','sick','maternity','personal','other')", name="ck_resource_leave_type"),
    )
    op.create_index(op.f("ix_resource_leave_resource_id"), "resource_leave", ["resource_id"])

    op.create_table(
        "resource_contract",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("hours_per_week", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["app_user.id"], name=op.f("fk_resource_contract_resource_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_resource_contract")),
        sa.CheckConstraint("status IN ('active','terminated')", name="ck_resource_contract_status"),
    )
    op.create_index(op.f("ix_resource_contract_resource_id"), "resource_contract", ["resource_id"])

    op.create_table(
        "bau_baseline",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("bau_percent", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["app_user.id"], name=op.f("fk_bau_baseline_resource_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bau_baseline")),
        sa.UniqueConstraint("resource_id", name=op.f("uq_bau_baseline_resource_id")),
        sa.CheckConstraint("bau_percent BETWEEN 0 AND 100", name="ck_bau_baseline_percent"),
    )

    op.create_table(
        "escalation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=True),
        sa.Column("competency_id", sa.Uuid(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("impact_cascade", sa.Text(), nullable=True),
        sa.Column("recommended_actions", sa.JSON(), nullable=False),
        sa.Column("required_decision", sa.Text(), nullable=True),
        sa.Column("target_role", sa.String(length=50), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("acknowledged_by", sa.Uuid(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_item.id"], name=op.f("fk_escalation_work_item_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competency_id"], ["competency.id"], name=op.f("fk_escalation_competency_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["acknowledged_by"], ["app_user.id"], name=op.f("fk_escalation_acknowledged_by"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_escalation")),
        sa.CheckConstraint("status IN ('open','acknowledged','closed')", name="ck_escalation_status"),
    )
    op.create_index(op.f("ix_escalation_work_item_id"), "escalation", ["work_item_id"])
    op.create_index(op.f("ix_escalation_competency_id"), "escalation", ["competency_id"])

    op.create_table(
        "scenario",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("promoted", sa.Boolean(), nullable=False),
        sa.Column("approved_by_id", sa.Uuid(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("expired", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["app_user.id"], name=op.f("fk_scenario_author_id"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["app_user.id"], name=op.f("fk_scenario_approved_by_id"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario")),
    )
    op.create_index(op.f("ix_scenario_author_id"), "scenario", ["author_id"])

    op.create_table(
        "scenario_change",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scenario_id", sa.Uuid(), nullable=False),
        sa.Column("allocation_id", sa.Uuid(), nullable=True),
        sa.Column("work_item_id", sa.Uuid(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario.id"], name=op.f("fk_scenario_change_scenario_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["allocation_id"], ["allocation.id"], name=op.f("fk_scenario_change_allocation_id"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_item_id"], ["work_item.id"], name=op.f("fk_scenario_change_work_item_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenario_change")),
    )
    op.create_index(op.f("ix_scenario_change_scenario_id"), "scenario_change", ["scenario_id"])
    op.create_index(op.f("ix_scenario_change_allocation_id"), "scenario_change", ["allocation_id"])
    op.create_index(op.f("ix_scenario_change_work_item_id"), "scenario_change", ["work_item_id"])


def downgrade() -> None:
    op.drop_table("scenario_change")
    op.drop_table("scenario")
    op.drop_table("escalation")
    op.drop_table("bau_baseline")
    op.drop_table("resource_contract")
    op.drop_table("resource_leave")
    op.drop_table("resource_calendar")
    op.drop_table("certification")
    op.drop_table("resource_skill")
    op.drop_table("competency")
