"""P6 milestone integration (plan §10, Phase 5, T5.5).

``bind_p6_project`` binds a work item (the delivery project) to a ``p6-sim``
project via ``external_ref``. ``read_project_from_p6`` pulls activities from the
sim, ingests them via the Phase-3 reconciliation pipeline, syncs statuses
(``activity_status`` → work item status) and maps activities to milestones
(per activity, a milestone child of the project).
"""

from __future__ import annotations

from uuid import UUID

from connectors.sdk.registry import get_connector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.graph.cache import graph_cache
from eil.modules.integration.ingestion import upsert_record
from eil.modules.integration.models import ApprovedSource, ExternalRef

ACTIVITY_TO_STATUS: dict[str, str] = {
    "complete": "completed",
    "completed": "completed",
    "finished": "completed",
    "in progress": "active",
    "inprogress": "active",
    "scheduled": "active",
    "not started": "draft",
    "blocked": "on_hold",
    "cancelled": "cancelled",
}

P6_URL = "https://p6.example.invalid"


async def bind_p6_project(
    session: AsyncSession, source: ApprovedSource, project_id: UUID, p6_project_id: str
) -> ExternalRef:
    """Bind the work item to the P6 project (idempotent)."""
    ref = (
        (
            await session.execute(
                select(ExternalRef).where(
                    ExternalRef.system == source.type,
                    ExternalRef.external_id == p6_project_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if ref is None:
        ref = ExternalRef(
            work_item_id=project_id,
            system=source.type,
            external_id=p6_project_id,
            external_url=f"{P6_URL}/projects/{p6_project_id}",
            owned_fields=["*"],
            is_simulated=True,
        )
        session.add(ref)
    else:
        ref.work_item_id = project_id
    await session.commit()
    return ref


async def read_project_from_p6(
    session: AsyncSession, source: ApprovedSource, project_id: UUID, *, max_records: int = 200
) -> int:
    """Pull activities from the bound P6 project and ingest them (T5.5)."""
    connector = get_connector(source.type)
    count = 0
    for raw in connector.pull(None):
        if raw.canonical_type not in ("activity", "milestone"):
            continue
        count += 1
        if count > max_records:
            break
        item = await upsert_record(session, source, connector, raw)
        if item is not None:
            await _map_activity(session, item, project_id)
    await session.commit()
    graph_cache.invalidate()
    return count


async def _map_activity(session: AsyncSession, item: WorkItem, project_id: UUID) -> None:
    """Sync status + dates from the activity record onto the work item."""
    attributes = item.attributes or {}
    status = str(
        attributes.get("status") or (attributes.get("canonical") or {}).get("status") or ""
    ).lower()
    mapped = ACTIVITY_TO_STATUS.get(status)
    if mapped and mapped != item.status:
        item.status = mapped
    forecast_end = attributes.get("forecast_end") or (attributes.get("canonical") or {}).get(
        "forecast_end"
    )
    if item.planned_end is not None and forecast_end:
        item.attributes["forecast_variance_days"] = int(
            item.attributes["forecast_end"] - item.planned_end
        )
    if not (
        (
            await session.execute(
                select(WorkLink).where(
                    WorkLink.src_id == item.id,
                    WorkLink.dst_id == project_id,
                    WorkLink.link_type.in_(("part_of", "aligns_to")),
                )
            )
        )
        .scalars()
        .first()
    ):
        session.add(
            WorkLink(
                src_id=item.id,
                dst_id=project_id,
                link_type="part_of",
                origin="system",
                status="active",
                weight=1,
            )
        )
    session.add(item)

    # Map activities to milestones: create a milestone per activity without one.
    if item.type == WorkType.TASK and item.planned_end is not None:
        has_children = (
            (
                await session.execute(
                    select(WorkLink).where(
                        WorkLink.dst_id == item.id,
                        WorkLink.link_type == "part_of",
                        WorkLink.status == "active",
                    )
                )
            )
            .scalars()
            .first()
        )
        if has_children is None:
            milestone = WorkItem(
                type=WorkType.MILESTONE,
                title=f"{item.title} completion",
                status="active",
                origin="external",
                attributes={
                    "source": "p6-sim",
                    "activity_code": (item.attributes or {}).get("activity_code"),
                },
                planned_end=item.planned_end,
            )
            session.add(milestone)
            await session.flush()
            session.add(
                WorkLink(
                    src_id=item.id,
                    dst_id=milestone.id,
                    link_type="part_of",
                    origin="system",
                    status="active",
                    weight=1,
                )
            )
            session.add(
                WorkLink(
                    src_id=milestone.id,
                    dst_id=project_id,
                    link_type="part_of",
                    origin="system",
                    status="active",
                    weight=1,
                )
            )
            session.add(milestone)
    await session.commit()
