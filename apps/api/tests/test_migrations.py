"""Alembic baseline migrates a clean SQLite database."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "migrated.db"
    env = os.environ.copy()
    env["APP_ENV"] = "ci"
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "0001_baseline" in (result.stdout + result.stderr)

    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "outbox" in tables

        for table in ("sod_rule", "workflow_def"):
            ids = [row[0] for row in connection.execute(f"SELECT id FROM {table}")]
            assert ids, f"{table} seed rows are missing"
            for value in ids:
                uuid.UUID(str(value))
    finally:
        connection.close()
