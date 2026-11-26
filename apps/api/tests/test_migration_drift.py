"""Migration drift audit — regression test (user-test finding: `score.created_at`).

Runs every alembic migration on a scratch SQLite database, then diffs the
resulting schema against ``Base.metadata`` (the app's source of truth):
every table and every model column must exist in the migrated database.
Catches drift like "model adds ``TimestampMixin`` columns after the
migration was written" (the ``score`` table lacked ``created_at``; the board
``GET /api/v1/prioritization`` 500'd on alembic-managed databases).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

import eil.main  # noqa: F401  — registers all models
from eil.core.db import Base

API_DIR = Path(__file__).resolve().parents[1]


def test_migrations_match_models(tmp_path: Path) -> None:
    db = tmp_path / "drift.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}{result.stderr}"

    engine = create_engine(f"sqlite:///{db}")
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    assert "score" in table_names

    drift: list[str] = []
    for table_name, table in sorted(Base.metadata.tables.items()):
        if table_name not in table_names:
            drift.append(f"{table_name}: table missing from migrations")
            continue
        db_columns = {c["name"] for c in inspector.get_columns(table_name)}
        absent = [column.name for column in table.columns if column.name not in db_columns]
        if absent:
            drift.append(f"{table_name}: missing columns {absent}")
    assert not drift, "Migration drift detected:\n" + "\n".join(drift)
