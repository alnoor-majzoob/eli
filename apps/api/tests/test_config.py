"""Local fallback path resolution."""

from __future__ import annotations

from pathlib import Path

from eil.core.config import REPO_ROOT, Settings


def test_relative_sqlite_url_resolves_against_repo_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./.data/test-relative.db")
    settings = Settings(_env_file=None)
    assert settings.sqlite_path == REPO_ROOT / ".data/test-relative.db"
    assert settings.database_url == (
        f"sqlite+aiosqlite:///{(REPO_ROOT / '.data/test-relative.db').as_posix()}"
    )


def test_absolute_sqlite_url_is_preserved(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'absolute.db'}"
    settings = Settings(_env_file=None, database_url=url)
    assert settings.database_url == url


def test_relative_object_store_dir_resolves_against_repo_root() -> None:
    settings = Settings(_env_file=None, object_store_local_dir="./.data/test-objects")
    assert settings.object_store_local_dir == REPO_ROOT / ".data/test-objects"
