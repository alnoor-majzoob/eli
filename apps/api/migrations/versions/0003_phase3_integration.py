"""Phase 3 — Integration hub: approved sources, external refs, artifacts, sync runs.

Revision ID: 0003_phase3_integration
Revises: 0002_phase2_work_graph
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase3_integration"
down_revision: str | None = "0002_phase2_work_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approved_source",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope_filters", sa.JSON(), nullable=False),
        sa.Column("owner", sa.String(length=200), nullable=False),
        sa.Column("classification", sa.String(length=30), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("ai_processing_allowed", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("owned_fields", sa.JSON(), nullable=False),
        sa.Column("write_back_enabled", sa.Boolean(), nullable=False),
        sa.Column("write_back_fields", sa.JSON(), nullable=False),
        sa.Column("write_back_requires_approval", sa.Boolean(), nullable=False),
        sa.Column("sync_cursor", sa.String(length=200), nullable=True),
        sa.Column("sync_lag_seconds", sa.Integer(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approved_source")),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f("fk_approved_source_created_by")
        ),
    )
    op.create_index(op.f("ix_approved_source_type"), "approved_source", ["type"])

    op.create_table(
        "external_ref",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("system", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("external_url", sa.String(length=500), nullable=True),
        sa.Column("owned_fields", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["work_item.id"], name=op.f("fk_external_ref_work_item_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_ref")),
        sa.UniqueConstraint("system", "external_id", name="uq_external_ref_binding"),
        sa.UniqueConstraint("work_item_id", name=op.f("uq_external_ref_work_item_id")),
    )
    op.create_index(op.f("ix_external_ref_work_item_id"), "external_ref", ["work_item_id"])

    op.create_table(
        "source_artifact",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("uri", sa.String(length=500), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("classification", sa.String(length=30), nullable=False),
        sa.Column("ai_processing_allowed", sa.Boolean(), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["source_id"], ["approved_source.id"], name=op.f("fk_source_artifact_source_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_artifact")),
    )
    op.create_index(op.f("ix_source_artifact_source_id"), "source_artifact", ["source_id"])

    op.create_table(
        "sync_run",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_count", sa.Integer(), nullable=True),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", sa.String(length=20), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["source_id"], ["approved_source.id"], name=op.f("fk_sync_run_source_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_run")),
    )
    op.create_index(op.f("ix_sync_run_source_id"), "sync_run", ["source_id"])
    op.create_index(op.f("ix_sync_run_status"), "sync_run", ["status"])

    op.create_table(
        "sync_conflict",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("external_value", sa.JSON(), nullable=True),
        sa.Column("local_value", sa.JSON(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["source_id"], ["approved_source.id"], name=op.f("fk_sync_conflict_source_id")
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["work_item.id"], name=op.f("fk_sync_conflict_work_item_id")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_conflict")),
    )
    op.create_index(op.f("ix_sync_conflict_source_id"), "sync_conflict", ["source_id"])
    op.create_index(
        op.f("ix_sync_conflict_work_item_id"), "sync_conflict", ["work_item_id"]
    )

    op.create_table(
        "write_back_change",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("work_item_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["source_id"], ["approved_source.id"], name=op.f("fk_write_back_change_source_id")
        ),
        sa.ForeignKeyConstraint(
            ["work_item_id"],
            ["work_item.id"],
            name=op.f("fk_write_back_change_work_item_id"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["app_user.id"], name=op.f("fk_write_back_change_approved_by")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_write_back_change")),
    )
    op.create_index(op.f("ix_write_back_change_source_id"), "write_back_change", ["source_id"])
    op.create_index(op.f("ix_write_back_change_work_item_id"), "write_back_change", ["work_item_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_write_back_change_work_item_id"), table_name="write_back_change")
    op.drop_index(op.f("ix_write_back_change_source_id"), table_name="write_back_change")
    op.drop_table("write_back_change")
    op.drop_index(op.f("ix_sync_conflict_work_item_id"), table_name="sync_conflict")
    op.drop_index(op.f("ix_sync_conflict_source_id"), table_name="sync_conflict")
    op.drop_table("sync_conflict")
    op.drop_index(op.f("ix_sync_run_status"), table_name="sync_run")
    op.drop_index(op.f("ix_sync_run_source_id"), table_name="sync_run")
    op.drop_table("sync_run")
    op.drop_index(op.f("ix_source_artifact_source_id"), table_name="source_artifact")
    op.drop_table("source_artifact")
    op.drop_index(op.f("ix_external_ref_work_item_id"), table_name="external_ref")
    op.drop_table("external_ref")
    op.drop_index(op.f("ix_approved_source_type"), table_name="approved_source")
    op.drop_table("approved_source")
