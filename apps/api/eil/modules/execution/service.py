"""Core execution service: work-item CRUD, graph links, benefit measurements."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.core.models import utcnow
from eil.modules.audit.service import record_audit
from eil.modules.execution.models import (
    LINK_TYPES,
    BenefitMeasurement,
    LinkTypeRule,
    WorkItem,
    WorkItemStatus,
    WorkLink,
    WorkType,
)
from eil.modules.execution.schemas import BenefitRollupRow, WorkItemPage
from eil.modules.graph.cache import graph_cache
from eil.modules.identity.models import OrgUnit, User
from eil.modules.identity.rbac import PermissionContext, resolve_permission_scope
from eil.modules.seed_data import DEMAND_CREATE, WORK_EDIT

WORKFLOW_STATUSES = {
    WorkItemStatus.SUBMITTED,
    WorkItemStatus.APPROVED,
    WorkItemStatus.REJECTED,
}

_DIRECT_TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "objective": {
        "draft": {"active", "cancelled"},
        "active": {"on_hold", "completed", "cancelled"},
        "on_hold": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    },
    "key_result": {
        "draft": {"active", "cancelled"},
        "active": {"on_hold", "completed", "cancelled"},
        "on_hold": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    },
    "initiative": {
        "draft": {"active", "cancelled"},
        "active": {"on_hold", "completed", "cancelled"},
        "on_hold": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    },
    "demand": {
        "draft": {"cancelled"},
        "submitted": {"cancelled"},
        "approved": {"active", "cancelled"},
        "rejected": {"draft", "cancelled"},
        "active": {"on_hold", "completed", "cancelled"},
        "on_hold": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    },
    "program": {
        "draft": {"cancelled"},
        "submitted": {"cancelled"},
        "approved": {"active", "cancelled"},
        "rejected": {"draft", "cancelled"},
        "active": {"on_hold", "completed", "cancelled"},
        "on_hold": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    },
    "project": {
        "draft": {"cancelled"},
        "submitted": {"cancelled"},
        "approved": {"active", "cancelled"},
        "rejected": {"draft", "cancelled"},
        "active": {"on_hold", "completed", "cancelled"},
        "on_hold": {"active", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    },
}

_PARENT_TYPES: dict[str, set[str]] = {
    "key_result": {"objective"},
    "initiative": {"objective", "key_result"},
    "demand": {"objective", "initiative"},
    "program": {"objective", "initiative"},
    "project": {"program", "initiative", "objective"},
    "milestone": {"project", "program"},
    "task": {"milestone", "project", "program", "demand", "initiative"},
    "commitment": {"project", "program", "objective", "initiative"},
    "risk": {"project", "program", "task", "objective"},
    "issue": {"project", "program", "task", "objective"},
    "benefit": {"objective", "key_result", "initiative", "project", "program"},
    "decision": {str(item) for item in WorkType if item != WorkType.DECISION},
}

_ALL_TYPES = {str(item) for item in WorkType}
_LINK_DST_TYPES: dict[str, set[str]] = {
    "part_of": _ALL_TYPES - {"objective"},
    "aligns_to": {"objective", "key_result"},
    "fulfils": {"commitment"},
    "realizes": {"benefit"},
    "mitigates": {"risk", "issue"},
    "threatens": set(_ALL_TYPES),
    "depends_on": set(_ALL_TYPES),
    "duplicate_of": set(_ALL_TYPES),
    "related_to": set(_ALL_TYPES),
    "derived_from": set(_ALL_TYPES),
    "assigned_to": set(_ALL_TYPES),
}

_LINK_SRC_TYPES: dict[str, set[str]] = {
    "aligns_to": {"initiative", "demand", "task", "project", "commitment"},
    "fulfils": {"task", "commitment", "project"},
    "realizes": {"project", "initiative", "program"},
    "mitigates": {"task", "project", "program"},
    "threatens": {"risk", "issue"},
    "derived_from": set(_ALL_TYPES),
}


def authorize_work_item(ctx: PermissionContext, item: WorkItem) -> None:
    if not ctx.can_access_org(item.org_unit_id):
        raise AppError(404, "not_found", "Not found", "Work item not found or not visible.")


async def get_work_item(session: AsyncSession, item_id: UUID, ctx: PermissionContext) -> WorkItem:
    item = (
        await session.execute(select(WorkItem).where(WorkItem.id == item_id))
    ).scalar_one_or_none()
    if item is None:
        raise AppError(404, "not_found", "Not found", "Work item not found.")
    authorize_work_item(ctx, item)
    return item


def _audit_view(item: WorkItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "type": item.type,
        "status": item.status,
        "title": item.title,
        "org_unit_id": str(item.org_unit_id) if item.org_unit_id else None,
        "version": item.version,
    }


async def _assert_create_permission(
    session: AsyncSession, ctx: PermissionContext, work_type: WorkType
) -> str:
    permission = DEMAND_CREATE if work_type == WorkType.DEMAND else WORK_EDIT
    scope = await resolve_permission_scope(session, ctx.roles, permission)
    if scope == "none":
        raise AppError(
            403,
            "forbidden",
            "Insufficient permissions",
            f"Missing permission '{permission}' for your role(s).",
            extra={"permission": permission},
        )
    return scope


async def _check_org(session: AsyncSession, org_unit_id: UUID | None) -> None:
    if org_unit_id is None:
        return
    exists = (
        await session.execute(select(OrgUnit.id).where(OrgUnit.id == org_unit_id))
    ).scalar_one_or_none()
    if exists is None:
        raise AppError(422, "validation_error", "Validation error", "Unknown org unit.")


async def _check_owner(session: AsyncSession, owner_id: UUID | None) -> None:
    if owner_id is None:
        return
    exists = (
        await session.execute(select(User.id).where(User.id == owner_id))
    ).scalar_one_or_none()
    if exists is None:
        raise AppError(422, "validation_error", "Validation error", "Unknown owner.")


async def _check_parent(
    session: AsyncSession,
    ctx: PermissionContext,
    work_type: str,
    parent_id: UUID | None,
    *,
    item_id: UUID | None = None,
) -> WorkItem | None:
    if parent_id is None:
        return None
    parent = await get_work_item(session, parent_id, ctx)
    allowed = _PARENT_TYPES.get(work_type, set())
    if allowed and parent.type not in allowed:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            f"A {work_type} cannot be parented by a {parent.type}.",
            extra={"allowed_parent_types": sorted(allowed)},
        )
    seen: set[UUID] = set()
    cursor: UUID | None = parent.id
    while cursor is not None:
        if item_id is not None and cursor == item_id:
            raise AppError(409, "conflict", "Conflict", "Parent hierarchy contains a cycle.")
        if cursor in seen:
            raise AppError(409, "conflict", "Conflict", "Parent hierarchy contains a cycle.")
        seen.add(cursor)
        cursor = (
            await session.execute(select(WorkItem.parent_id).where(WorkItem.id == cursor))
        ).scalar_one_or_none()
    return parent


def _check_status_transition(item: WorkItem, new_status: str) -> None:
    if new_status == item.status:
        return
    if new_status in WORKFLOW_STATUSES:
        raise AppError(
            409,
            "conflict",
            "Conflict",
            "Workflow statuses can only change through submit/approve/reject.",
            extra={"status": new_status},
        )
    transitions = _DIRECT_TRANSITIONS.get(item.type)
    if transitions is None:
        transitions = {
            "draft": {"active", "cancelled"},
            "active": {"on_hold", "completed", "cancelled"},
            "on_hold": {"active", "cancelled"},
            "completed": set(),
            "cancelled": set(),
        }
    allowed = transitions.get(item.status, set())
    if new_status not in allowed:
        raise AppError(
            409,
            "invalid_transition",
            "Invalid transition",
            f"Cannot move a {item.type} from '{item.status}' to '{new_status}'.",
            extra={"from": item.status, "allowed": sorted(allowed)},
        )


async def list_work_items(
    session: AsyncSession,
    ctx: PermissionContext,
    *,
    types: Sequence[WorkType] | None = None,
    statuses: Sequence[WorkItemStatus] | None = None,
    org_unit_id: UUID | None = None,
    parent_id: UUID | None = None,
    owner_id: UUID | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> WorkItemPage:
    filters: list[Any] = []
    if types:
        filters.append(WorkItem.type.in_(types))
    if statuses:
        filters.append(WorkItem.status.in_(statuses))
    if org_unit_id is not None:
        filters.append(WorkItem.org_unit_id == org_unit_id)
    if parent_id is not None:
        filters.append(WorkItem.parent_id == parent_id)
    if owner_id is not None:
        filters.append(WorkItem.owner_id == owner_id)
    if search:
        filters.append(WorkItem.title.ilike(f"%{search}%"))
    if ctx.scope == "own_org":
        filters.append(WorkItem.org_unit_id == ctx.user.org_unit_id)

    base = select(WorkItem)
    if filters:
        base = base.where(*filters)
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    )
    ordered = (
        base.order_by(WorkItem.updated_at.desc(), WorkItem.id.desc()).limit(limit).offset(offset)
    )
    rows = list((await session.execute(ordered)).scalars().all())
    return WorkItemPage(items=rows, total=total, limit=limit, offset=offset)


async def create_work_item(session: AsyncSession, ctx: PermissionContext, payload: Any) -> WorkItem:
    data = payload.model_dump()
    data.pop("id", None)
    data.pop("version", None)
    work_type = WorkType(data["type"])
    scope = await _assert_create_permission(session, ctx, work_type)
    requested_status = data.get("status", WorkItemStatus.DRAFT)
    if requested_status != WorkItemStatus.DRAFT:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            "New work items must start in draft; use transitions or workflows afterwards.",
        )

    parent = await _check_parent(session, ctx, work_type.value, data.get("parent_id"))
    if scope == "own_org":
        data["org_unit_id"] = ctx.user.org_unit_id
    elif data.get("org_unit_id") is None:
        data["org_unit_id"] = parent.org_unit_id if parent else ctx.user.org_unit_id
    await _check_org(session, data.get("org_unit_id"))
    await _check_owner(session, data.get("owner_id"))

    attributes = data.get("attributes") or {}
    rag = attributes.get("rag")
    if rag is not None and rag not in {"green", "amber", "red"}:
        raise AppError(422, "validation_error", "Validation error", "rag must be green/amber/red.")
    data["attributes"] = attributes
    data["created_by"] = ctx.user.id

    item = WorkItem(**data)
    session.add(item)
    await session.commit()
    await session.refresh(item)

    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_item.created",
        entity_type="work_item",
        entity_id=item.id,
        org_unit_id=item.org_unit_id,
        after=_audit_view(item),
        reason=f"Created {item.type}.",
    )
    await session.commit()
    graph_cache.invalidate()
    return item


async def update_work_item(
    session: AsyncSession,
    ctx: PermissionContext,
    item: WorkItem,
    payload: Any,
    *,
    expected_version: int | None = None,
) -> WorkItem:
    data = payload.model_dump(exclude_unset=True)
    data.pop("id", None)
    data.pop("created_by", None)
    if expected_version is not None and expected_version != item.version:
        raise AppError(
            412,
            "precondition_failed",
            "Precondition failed",
            "Work item has changed; reload before updating.",
            extra={"version": item.version},
        )
    body_version = data.pop("version", None)
    if body_version is not None and body_version != item.version:
        raise AppError(
            409,
            "conflict",
            "Conflict",
            "Work item version is out of date.",
            extra={"version": item.version},
        )
    if "type" in data and data["type"] != item.type:
        raise AppError(422, "validation_error", "Validation error", "The item type is immutable.")
    if "status" in data:
        _check_status_transition(item, data["status"])
    if "parent_id" in data:
        parent = await _check_parent(session, ctx, item.type, data["parent_id"], item_id=item.id)
        if parent is not None and parent.id == item.id:
            raise AppError(
                422, "validation_error", "Validation error", "An item cannot parent itself."
            )
    else:
        parent = None
    if ctx.scope == "own_org" and "org_unit_id" in data:
        data["org_unit_id"] = ctx.user.org_unit_id
    if "org_unit_id" in data:
        await _check_org(session, data["org_unit_id"])
    if "owner_id" in data:
        await _check_owner(session, data["owner_id"])
    if "attributes" in data:
        attributes = data["attributes"] or {}
        rag = attributes.get("rag")
        if rag is not None and rag not in {"green", "amber", "red"}:
            raise AppError(
                422, "validation_error", "Validation error", "rag must be green/amber/red."
            )
        data["attributes"] = attributes

    before = _audit_view(item)
    if parent is not None and item.org_unit_id is None:
        item.org_unit_id = parent.org_unit_id
    for key, value in data.items():
        setattr(item, key, value)
    if data.get("completed_percent") is not None:
        attributes = item.attributes or {}
        attributes["completed_percent"] = float(data["completed_percent"])
        item.attributes = attributes
    item.updated_at = utcnow()
    item.version += 1
    await session.commit()
    await session.refresh(item)

    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_item.updated",
        entity_type="work_item",
        entity_id=item.id,
        org_unit_id=item.org_unit_id,
        before=before,
        after=_audit_view(item),
        reason="Work item updated.",
    )
    await session.commit()
    graph_cache.invalidate()
    return item


async def delete_work_item(session: AsyncSession, ctx: PermissionContext, item: WorkItem) -> None:
    if item.status not in {"draft", "rejected", "cancelled"} and not ctx.is_admin:
        raise AppError(
            409,
            "conflict",
            "Conflict",
            "Only draft, rejected or cancelled items can be deleted.",
        )
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_item.deleted",
        entity_type="work_item",
        entity_id=item.id,
        org_unit_id=item.org_unit_id,
        before=_audit_view(item),
        reason="Work item deleted.",
    )
    await session.delete(item)
    await session.commit()
    graph_cache.invalidate()


def _assert_link_allowed(src: WorkItem, dst: WorkItem, link_type: str) -> None:
    if src.id == dst.id:
        raise AppError(
            422, "validation_error", "Validation error", "An item cannot link to itself."
        )
    allowed_dst = _LINK_DST_TYPES.get(link_type)
    if allowed_dst is not None and dst.type not in allowed_dst:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            f"'{link_type}' cannot target a {dst.type}.",
            extra={"allowed_targets": sorted(allowed_dst)},
        )
    allowed_src = _LINK_SRC_TYPES.get(link_type)
    if allowed_src is not None and src.type not in allowed_src:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            f"'{link_type}' cannot originate from a {src.type}.",
            extra={"allowed_sources": sorted(allowed_src)},
        )
    if link_type == "duplicate_of" and src.type != dst.type:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            "Duplicates must share the same item type.",
        )


async def _link_rule_row(
    session: AsyncSession, src: WorkItem, dst: WorkItem, link_type: str
) -> LinkTypeRule | None:
    return (
        await session.execute(
            select(LinkTypeRule).where(
                LinkTypeRule.src_type == src.type,
                LinkTypeRule.dst_type == dst.type,
                LinkTypeRule.link_type == link_type,
            )
        )
    ).scalar_one_or_none()


async def _table_has_rules(session: AsyncSession) -> bool:
    return (await session.execute(select(LinkTypeRule.id).limit(1))).first() is not None


async def _seed_link_type_rules(session: AsyncSession) -> None:
    """Seed the whitelist from the built-in rule tables.

    Production databases get the seed from the ``0002_phase2_work_graph`` migration;
    the lazy seed covers ``Base.metadata.create_all`` flows (tests, fresh engines).
    """
    combos: set[tuple[str, str, str]] = set()
    for link_type in LINK_TYPES:
        srcs = _LINK_SRC_TYPES.get(link_type, set(_ALL_TYPES))
        dsts = _LINK_DST_TYPES.get(link_type, set(_ALL_TYPES))
        combos.update((src, dst, link_type) for src in srcs for dst in dsts)
    session.add_all(
        LinkTypeRule(src_type=src, dst_type=dst, link_type=link)
        for src, dst, link in sorted(combos)
    )
    await session.flush()


async def _assert_link_rule(
    session: AsyncSession, src: WorkItem, dst: WorkItem, link_type: str
) -> None:
    """Reject a link when the (src_type, dst_type, link_type) combo is not whitelisted
    in ``link_type_rule`` (plan §7.2)."""
    rule = await _link_rule_row(session, src, dst, link_type)
    if rule is None and not await _table_has_rules(session):
        await _seed_link_type_rules(session)
        rule = await _link_rule_row(session, src, dst, link_type)
    if rule is None:
        raise AppError(
            422,
            "validation_error",
            "Validation error",
            f"'{link_type}' is not a valid link between a {src.type} and a {dst.type}.",
            extra={
                "link_type": link_type,
                "src_type": src.type,
                "dst_type": dst.type,
            },
        )


async def _would_cycle(session: AsyncSession, src_id: UUID, dst_id: UUID, link_type: str) -> bool:
    """Return True when adding src -> dst would create a cycle of the given type."""
    frontier = [dst_id]
    seen: set[UUID] = set()
    while frontier:
        current = frontier.pop()
        if current == src_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        rows = (
            await session.execute(
                select(WorkLink.dst_id).where(
                    WorkLink.src_id == current,
                    WorkLink.link_type == link_type,
                    WorkLink.status == "active",
                )
            )
        ).scalars()
        frontier.extend(rows)
    return False


async def list_work_links(
    session: AsyncSession, item: WorkItem, direction: str = "both"
) -> list[WorkLink]:
    if direction == "out":
        stmt = select(WorkLink).where(WorkLink.src_id == item.id)
    elif direction == "in":
        stmt = select(WorkLink).where(WorkLink.dst_id == item.id)
    else:
        stmt = select(WorkLink).where((WorkLink.src_id == item.id) | (WorkLink.dst_id == item.id))
    result = await session.execute(stmt.order_by(WorkLink.created_at, WorkLink.id))
    return list(result.scalars().all())


async def create_work_link(
    session: AsyncSession, ctx: PermissionContext, src_id: UUID, payload: Any
) -> WorkLink:
    src = await get_work_item(session, src_id, ctx)
    dst = await get_work_item(session, payload.dst_id, ctx)
    link_type = str(payload.link_type)
    _assert_link_allowed(src, dst, link_type)
    await _assert_link_rule(session, src, dst, link_type)

    existing = (
        await session.execute(
            select(WorkLink).where(
                WorkLink.src_id == src.id,
                WorkLink.dst_id == dst.id,
                WorkLink.link_type == link_type,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            409,
            "conflict",
            "Conflict",
            "This link already exists.",
            extra={"link_id": str(existing.id)},
        )
    if link_type in {"depends_on", "part_of"} and await _would_cycle(
        session, src.id, dst.id, link_type
    ):
        raise AppError(
            409,
            "cycle_detected",
            "Cycle detected",
            f"Adding this '{link_type}' link would create a cycle.",
        )

    data = payload.model_dump(exclude={"src_id"})
    data.update({"src_id": src.id, "dst_id": dst.id, "created_by": ctx.user.id})
    link = WorkLink(**data)
    session.add(link)
    await session.commit()
    await session.refresh(link)

    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_link.created",
        entity_type="work_link",
        entity_id=link.id,
        org_unit_id=src.org_unit_id,
        after={"src_id": str(src.id), "dst_id": str(dst.id), "link_type": link_type},
        reason="Work link created.",
    )
    await session.commit()
    graph_cache.invalidate()
    return link


async def delete_work_link(
    session: AsyncSession, ctx: PermissionContext, item: WorkItem, link_id: UUID
) -> None:
    link = (
        await session.execute(
            select(WorkLink).where(
                WorkLink.id == link_id,
                (WorkLink.src_id == item.id) | (WorkLink.dst_id == item.id),
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise AppError(404, "not_found", "Not found", "Work link not found.")
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="work_link.deleted",
        entity_type="work_link",
        entity_id=link.id,
        org_unit_id=item.org_unit_id,
        before={
            "src_id": str(link.src_id),
            "dst_id": str(link.dst_id),
            "link_type": link.link_type,
        },
        reason="Work link deleted.",
    )
    await session.delete(link)
    await session.commit()
    graph_cache.invalidate()


async def get_benefit_measurements(
    session: AsyncSession, benefit_id: UUID
) -> list[BenefitMeasurement]:
    result = await session.execute(
        select(BenefitMeasurement)
        .where(BenefitMeasurement.benefit_id == benefit_id)
        .order_by(BenefitMeasurement.period, BenefitMeasurement.id)
    )
    return list(result.scalars().all())


async def create_benefit_measurement(
    session: AsyncSession, ctx: PermissionContext, benefit: WorkItem, payload: Any
) -> BenefitMeasurement:
    if benefit.type != WorkType.BENEFIT:
        raise AppError(422, "validation_error", "Validation error", "Item is not a benefit.")
    existing = (
        await session.execute(
            select(BenefitMeasurement).where(
                BenefitMeasurement.benefit_id == benefit.id,
                BenefitMeasurement.period == payload.period,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(409, "conflict", "Conflict", "A measurement for this period exists.")
    data = payload.model_dump()
    measurement = BenefitMeasurement(**data, benefit_id=benefit.id, created_by=ctx.user.id)
    session.add(measurement)
    await session.commit()
    await session.refresh(measurement)
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="benefit.measurement_created",
        entity_type="work_item",
        entity_id=benefit.id,
        org_unit_id=benefit.org_unit_id,
        after={"period": measurement.period.isoformat(), "actual": str(measurement.actual)},
        reason="Benefit measurement recorded.",
    )
    await session.commit()
    return measurement


async def update_benefit_measurement(
    session: AsyncSession, ctx: PermissionContext, measurement: BenefitMeasurement, payload: Any
) -> BenefitMeasurement:
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(measurement, key, value)
    measurement.updated_at = utcnow()
    await session.commit()
    await session.refresh(measurement)
    await record_audit(
        session,
        actor_id=ctx.principal.subject,
        actor_type="user",
        action="benefit.measurement_updated",
        entity_type="work_item",
        entity_id=measurement.benefit_id,
        after={"period": measurement.period.isoformat(), "actual": str(measurement.actual)},
        reason="Benefit measurement updated.",
    )
    await session.commit()
    return measurement


async def get_benefit_realisation(session: AsyncSession, benefit: WorkItem) -> dict[str, Any]:
    measurements = await get_benefit_measurements(session, benefit.id)
    if not measurements:
        return {
            "benefit_id": benefit.id,
            "baseline": None,
            "target": None,
            "latest_actual": None,
            "latest_forecast": None,
            "realisation_pct": None,
            "forecast_pct": None,
            "as_of": None,
            "measurements": [],
        }

    baseline = next((m.baseline for m in measurements if m.baseline is not None), None)
    target = next((m.target for m in reversed(measurements) if m.target is not None), None)
    latest_actual = next((m.actual for m in reversed(measurements) if m.actual is not None), None)
    latest_forecast = next(
        (m.forecast for m in reversed(measurements) if m.forecast is not None), None
    )
    as_of = next(
        (
            m.period
            for m in reversed(measurements)
            if m.actual is not None or m.forecast is not None
        ),
        None,
    )

    def _pct(value: Decimal | None) -> Decimal | None:
        if value is None or baseline is None or target is None or target == baseline:
            return None
        return ((value - baseline) / (target - baseline) * 100).quantize(Decimal("0.001"))

    return {
        "benefit_id": benefit.id,
        "baseline": baseline,
        "target": target,
        "latest_actual": latest_actual,
        "latest_forecast": latest_forecast,
        "realisation_pct": _pct(latest_actual),
        "forecast_pct": _pct(latest_forecast),
        "as_of": as_of,
        "measurements": measurements,
    }


async def get_measurement(session: AsyncSession, measurement_id: UUID) -> BenefitMeasurement:
    measurement = (
        await session.execute(
            select(BenefitMeasurement).where(BenefitMeasurement.id == measurement_id)
        )
    ).scalar_one_or_none()
    if measurement is None:
        raise AppError(404, "not_found", "Not found", "Benefit measurement not found.")
    return measurement


async def benefit_rollup(session: AsyncSession, ctx: PermissionContext) -> list[BenefitRollupRow]:
    """Benefits → KRs → objectives roll-up for strategic outcome widgets (plan Phase 5, T5.7).

    For each active objective: benefits realized through ``realizes`` links,
    key results aligned through ``aligns_to`` links, and the benefit-measurement
    roll-up (actual/target/forecast) with an on-track flag.
    """
    objectives = (
        (
            await session.execute(
                select(WorkItem).where(
                    WorkItem.type == WorkType.OBJECTIVE,
                    WorkItem.status == WorkItemStatus.ACTIVE,
                )
            )
        )
        .scalars()
        .all()
    )
    rows: list[BenefitRollupRow] = []
    for objective in objectives:
        benefit_ids = [
            link.dst_id
            for link in (
                await session.execute(
                    select(WorkLink).where(
                        WorkLink.src_id == objective.id,
                        WorkLink.link_type == "realizes",
                        WorkLink.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        ]
        kr_ids = [
            link.dst_id
            for link in (
                await session.execute(
                    select(WorkLink).where(
                        WorkLink.src_id == objective.id,
                        WorkLink.link_type == "aligns_to",
                        WorkLink.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        ]
        kr_count = 0
        if kr_ids:
            kr_count = len(
                (
                    await session.execute(
                        select(WorkItem).where(
                            WorkItem.id.in_(kr_ids),
                            WorkItem.type == WorkType.KEY_RESULT,
                            WorkItem.status == WorkItemStatus.ACTIVE,
                        )
                    )
                )
                .scalars()
                .all()
            )
        measurements = (
            (
                await session.execute(
                    select(BenefitMeasurement).where(BenefitMeasurement.benefit_id.in_(benefit_ids))
                )
            )
            .scalars()
            .all()
            if benefit_ids
            else []
        )
        actuals = [m.actual for m in measurements if m.actual is not None]
        forecasts = [m.forecast for m in measurements if m.forecast is not None]
        targets = [m.target for m in measurements if m.target is not None]
        latest_actual_at = max(
            (m.period for m in measurements if m.actual is not None), default=None
        )
        on_track = True if not forecasts or not actuals else bool(max(actuals) >= max(forecasts))
        rows.append(
            BenefitRollupRow(
                objective_id=objective.id,
                title=objective.title,
                kr_count=kr_count,
                benefit_count=len(benefit_ids),
                total_actual=sum(actuals) if actuals else None,
                total_target=sum(targets) if targets else None,
                total_forecast=sum(forecasts) if forecasts else None,
                latest_actual_at=latest_actual_at,
                on_track=on_track,
            )
        )
    return rows


__all__ = [
    "_audit_view",
    "authorize_work_item",
    "benefit_rollup",
    "create_benefit_measurement",
    "create_work_item",
    "create_work_link",
    "delete_work_item",
    "delete_work_link",
    "get_benefit_measurements",
    "get_benefit_realisation",
    "get_measurement",
    "get_work_item",
    "list_work_items",
    "list_work_links",
    "update_benefit_measurement",
    "update_work_item",
]
