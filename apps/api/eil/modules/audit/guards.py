"""Database guards enforcing that the audit log is append-only.

SQLite and PostgreSQL triggers are installed idempotently at application startup
and in the test harness. Any UPDATE or DELETE on ``audit_log`` is rejected at the
database level, complementing the hash chain and application audit helper.
"""

from __future__ import annotations

import structlog
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = structlog.get_logger(__name__)

SQLITE_TRIGGERS = (
    """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_update
    BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit_log is append-only (UPDATE blocked)');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit_log is append-only (DELETE blocked)');
    END
    """,
)

POSTGRES_TRIGGERS = (
    """
    CREATE OR REPLACE FUNCTION eil_audit_append_only() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'audit_log is append-only (% blocked)', TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log",
    """
    CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION eil_audit_append_only()
    """,
)


async def install_audit_guards(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        dialect = connection.dialect.name
        try:
            table_exists = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).has_table("audit_log")
            )
            if not table_exists:
                logger.info("audit_guard_skipped_missing_table", dialect=dialect)
                return
            if dialect == "sqlite":
                for statement in SQLITE_TRIGGERS:
                    await connection.execute(text(statement))
            elif dialect == "postgresql":
                for statement in POSTGRES_TRIGGERS:
                    await connection.execute(text(statement))
        except Exception:  # pragma: no cover - defensive: never block startup
            logger.exception("audit_guard_install_failed", dialect=dialect)
