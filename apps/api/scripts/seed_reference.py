"""Seed Phase 1 reference data into an existing database.

Run after migrations have created the schema. This is safe to re-run; the seed
helpers are idempotent.

Usage (inside the API container):
    python scripts/seed_reference.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from eil.core.config import get_settings  # noqa: E402
from eil.core.db import create_engine, create_session_factory  # noqa: E402
from eil.modules.audit.guards import install_audit_guards  # noqa: E402
from eil.modules.seed import seed_reference_data  # noqa: E402


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        await install_audit_guards(engine)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            await seed_reference_data(session)
        target = engine.url.render_as_string(hide_password=True)
        print(f"Seeded reference data into {target}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
