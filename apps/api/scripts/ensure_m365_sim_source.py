"""Ensure an M365 sim ApprovedSource exists (idempotent).

Usage (inside API container):
    python scripts/ensure_m365_sim_source.py
    python scripts/ensure_m365_sim_source.py --enable-ai-processing
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from sqlalchemy import select  # noqa: E402

from eil.core.config import get_settings  # noqa: E402
from eil.core.db import create_engine, create_session_factory  # noqa: E402
from eil.modules.audit.guards import install_audit_guards  # noqa: E402
from eil.modules.integration.models import ApprovedSource  # noqa: E402


async def main(enable_ai_processing: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        await install_audit_guards(engine)
        session_factory = create_session_factory(engine)
        async with session_factory() as session:
            source = (
                (
                    await session.execute(
                        select(ApprovedSource)
                        .where(ApprovedSource.type == "m365")
                        .order_by(ApprovedSource.created_at, ApprovedSource.id)
                    )
                )
                .scalars()
                .first()
            )
            if source is None:
                source = ApprovedSource(
                    type="m365",
                    name="M365 Simulator",
                    description="Seeded M365 simulator source for dev/demo mail sync.",
                    owner="IT",
                    classification="internal",
                    ai_processing_allowed=enable_ai_processing,
                    enabled=True,
                )
                session.add(source)
                action = "created"
            else:
                source.enabled = True
                if enable_ai_processing:
                    source.ai_processing_allowed = True
                session.add(source)
                action = "updated"
            await session.commit()
            await session.refresh(source)
            print(
                f"{action} m365 source id={source.id} "
                f"enabled={source.enabled} ai_processing_allowed={source.ai_processing_allowed}"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--enable-ai-processing",
        action="store_true",
        help="Set ai_processing_allowed=true on the M365 source.",
    )
    args = parser.parse_args()
    asyncio.run(main(args.enable_ai_processing))
