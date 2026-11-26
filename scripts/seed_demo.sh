#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///$(pwd)/.data/eil.db}"
mkdir -p .data
uv run --directory apps/api python - <<'PY'
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from eil.core.config import Settings
from eil.core.db import Base
from eil.modules.audit.guards import install_audit_guards
from eil.modules.seed import seed_reference_data

async def main() -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await install_audit_guards(engine)
    async with AsyncSession(engine) as session:
        await seed_reference_data(session)
        await session.commit()
    await engine.dispose()
    print("Seeded synthetic EIL demo data at", Settings().database_url)

asyncio.run(main())
PY
