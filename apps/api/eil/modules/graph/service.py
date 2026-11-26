"""Enterprise Work Graph services: neighbours, lineage, path, downstream impact.

Follows plan §7.4 (impact-propagation semantics): ``depends_on`` edges are
reversed (predecessor → dependent); ``part_of``, ``aligns_to``, ``fulfils``,
``realizes`` and ``threatens`` propagate delay src → dst. ``assigned_to`` is
exposed to the graph API as a virtual edge unioned from ``work_item.owner_id``
and ``allocation``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.core.errors import AppError
from eil.modules.execution.models import Allocation, WorkItem, WorkLink, WorkType
from eil.modules.execution.service import get_work_item
from eil.modules.graph.cache import graph_cache
from eil.modules.graph.schemas import (
    DownstreamImpactRead,
    GraphEdgeRead,
    GraphNodeRead,
    ImpactItemRead,
    LineageRead,
    NeighborsRead,
    PathRead,
)
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext

LINEAGE_UP_LINK_TYPES = ("part_of", "aligns_to")
IMPACT_LINK_TYPES = ("part_of", "aligns_to", "fulfils", "realizes", "threatens")
MAX_LINEAGE_DEPTH = 10
MAX_IMPACT_DEPTH = 6

IMPACT_ONE = Decimal("1")
ZERO = Decimal("0")


@dataclass(frozen=True)
class EdgeRecord:
    id: UUID | None
    src_id: UUID
    dst_id: UUID
    link_type: str | None
    weight: Decimal | None
    origin: str | None
    status: str | None
    confidence: Decimal | None
    is_virtual: bool


def _d(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _is_simulated(item: WorkItem) -> bool:
    return item.origin == "external"


def _node_read(obj: WorkItem | User) -> GraphNodeRead:
    if isinstance(obj, WorkItem):
        return GraphNodeRead(
            id=obj.id,
            type=obj.type,
            title=obj.title,
            description=obj.description,
            status=obj.status,
            origin=obj.origin,
            owner_id=obj.owner_id,
            org_unit_id=obj.org_unit_id,
            attributes=obj.attributes or {},
            is_simulated=_is_simulated(obj),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )
    return GraphNodeRead(
        id=obj.id,
        type=None,
        title=obj.name or obj.subject,
        description=None,
        status=None,
        origin="resource",
        owner_id=None,
        org_unit_id=obj.org_unit_id,
        attributes={},
        is_simulated=False,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


async def _load_node_object(session: AsyncSession, node_id: UUID) -> WorkItem | User | None:
    """Load a graph-node endpoint: work item first, resource (owner) as fallback."""
    item = await _load_item(session, node_id)
    if item is not None:
        return item
    return (await session.execute(select(User).where(User.id == node_id))).scalar_one_or_none()


async def _load_item(session: AsyncSession, item_id: UUID) -> WorkItem | None:
    return (
        await session.execute(select(WorkItem).where(WorkItem.id == item_id))
    ).scalar_one_or_none()


async def _load_items(session: AsyncSession, item_ids: set[UUID]) -> dict[UUID, WorkItem]:
    if not item_ids:
        return {}
    ids = list(item_ids)
    items: dict[UUID, WorkItem] = {}
    for start in range(0, len(ids), 500):
        rows = (
            (
                await session.execute(
                    select(WorkItem).where(WorkItem.id.in_(ids[start : start + 500]))
                )
            )
            .scalars()
            .all()
        )
        for item in rows:
            items[item.id] = item
    return items


async def _load_real_edges(
    session: AsyncSession,
    item_ids: set[UUID],
    active_only: bool = True,
    link_types: tuple[str, ...] | list[str] | None = None,
) -> list[EdgeRecord]:
    """Load ``work_link`` rows touching any of ``item_ids`` as edge records.

    An empty ``item_ids`` means "all rows" (unfiltered) — used by integrity scans.
    """
    ids = list(item_ids)

    def _stmt_for(chunk: list[UUID] | None) -> Any:
        stmt = select(
            WorkLink.id,
            WorkLink.src_id,
            WorkLink.dst_id,
            WorkLink.link_type,
            WorkLink.weight,
            WorkLink.origin,
            WorkLink.status,
            WorkLink.confidence,
        )
        if chunk:
            stmt = stmt.where((WorkLink.src_id.in_(chunk)) | (WorkLink.dst_id.in_(chunk)))
        if active_only:
            stmt = stmt.where(WorkLink.status == "active")
        if link_types is not None:
            stmt = stmt.where(WorkLink.link_type.in_(link_types))
        return stmt.order_by(WorkLink.created_at, WorkLink.id)

    records: list[EdgeRecord] = []
    # Chunk for SQLite variable limits on very wide frontiers.
    chunks: list[list[UUID] | None] = [
        ids[start : start + 500] for start in range(0, len(ids), 500)
    ] or [None]
    for chunk in chunks:
        rows = (await session.execute(_stmt_for(chunk))).all()
        records.extend(
            EdgeRecord(
                id=row.id,
                src_id=row.src_id,
                dst_id=row.dst_id,
                link_type=row.link_type,
                weight=_d(row.weight) or ZERO,
                origin=row.origin,
                status=row.status,
                confidence=_d(row.confidence),
                is_virtual=False,
            )
            for row in rows
        )
    return records


async def _virtual_edges(session: AsyncSession, item_ids: set[UUID]) -> list[EdgeRecord]:
    """Virtual ``assigned_to`` edges: item → owner and item → allocation resource."""
    edges: list[EdgeRecord] = []
    if not item_ids:
        return edges
    items = (
        (await session.execute(select(WorkItem).where(WorkItem.id.in_(list(item_ids)))))
        .scalars()
        .all()
    )
    for item in items:
        if item.owner_id is not None:
            edges.append(
                EdgeRecord(
                    id=None,
                    src_id=item.id,
                    dst_id=item.owner_id,
                    link_type="assigned_to",
                    weight=Decimal("1"),
                    origin="system",
                    status="active",
                    confidence=None,
                    is_virtual=True,
                )
            )
    allocations = (
        (
            await session.execute(
                select(Allocation).where(Allocation.work_item_id.in_(list(item_ids)))
            )
        )
        .scalars()
        .all()
    )
    for allocation in allocations:
        if allocation.work_item_id is None or allocation.resource_id is None:
            continue
        edges.append(
            EdgeRecord(
                id=allocation.id,
                src_id=allocation.work_item_id,
                dst_id=allocation.resource_id,
                link_type="assigned_to",
                weight=Decimal("1"),
                origin="system",
                status="active",
                confidence=None,
                is_virtual=True,
            )
        )
    return edges


async def _edge_read(session: AsyncSession, record: EdgeRecord) -> GraphEdgeRead:
    src_obj = await _load_node_object(session, record.src_id)
    dst_obj = await _load_node_object(session, record.dst_id)
    if src_obj is None or dst_obj is None:
        raise AppError(404, "not_found", "Not found", "Graph edge endpoints are missing.")
    return GraphEdgeRead(
        id=record.id,
        src_id=record.src_id,
        dst_id=record.dst_id,
        link_type=record.link_type,
        weight=record.weight,
        origin=record.origin,
        status=record.status,
        confidence=record.confidence,
        is_virtual=record.is_virtual,
        src=_node_read(src_obj),
        dst=_node_read(dst_obj),
    )


async def neighbours(
    session: AsyncSession,
    ctx: PermissionContext,
    item_id: UUID,
    direction: str = "both",
    include_virtual: bool = True,
) -> NeighborsRead:
    key = f"neighbours:{item_id}:{direction}:{include_virtual}"
    cached: NeighborsRead | None = graph_cache.get(key)
    if cached is not None:
        return cached

    item = await get_work_item(session, item_id, ctx)
    records = await _load_real_edges(session, {item.id})
    if include_virtual:
        records += await _virtual_edges(session, {item.id})
    if direction == "out":
        records = [record for record in records if record.src_id == item.id]
    elif direction == "in":
        records = [record for record in records if record.dst_id == item.id]
    result = NeighborsRead(
        node_id=item.id,
        node=_node_read(item),
        edges=[await _edge_read(session, record) for record in records],
    )
    graph_cache.set(key, result)
    return result


async def _next_up(session: AsyncSession, node_id: UUID) -> WorkItem | None:
    """Return the next item up the lineage chain (part_of preferred over aligns_to)."""
    stmt = (
        select(WorkItem, WorkLink)
        .join(WorkLink, WorkLink.dst_id == WorkItem.id)
        .where(
            WorkLink.src_id == node_id,
            WorkLink.status == "active",
            WorkLink.link_type.in_(LINEAGE_UP_LINK_TYPES),
        )
        .order_by(WorkLink.created_at, WorkLink.id)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return None
    for item, link in rows:
        if link.link_type == "part_of":
            return item
    return rows[0][0]


async def lineage(
    session: AsyncSession,
    ctx: PermissionContext,
    item_id: UUID,
    max_depth: int = MAX_LINEAGE_DEPTH,
) -> LineageRead:
    key = f"lineage:{item_id}:{max_depth}"
    cached: LineageRead | None = graph_cache.get(key)
    if cached is not None:
        return cached

    item = await get_work_item(session, item_id, ctx)
    chain = [item]
    seen = {item.id}
    current_id = item.id
    for _ in range(max_depth):
        nxt = await _next_up(session, current_id)
        if nxt is None or nxt.id in seen:
            break
        chain.append(nxt)
        seen.add(nxt.id)
        current_id = nxt.id
        if nxt.type == WorkType.OBJECTIVE:
            break

    result = LineageRead(items=[_node_read(node) for node in chain])
    graph_cache.set(key, result)
    return result


async def path(
    session: AsyncSession,
    ctx: PermissionContext,
    from_id: UUID,
    to_id: UUID,
    include_virtual: bool = True,
) -> PathRead:
    key = f"path:{from_id}:{to_id}:{include_virtual}"
    cached: PathRead | None = graph_cache.get(key)
    if cached is not None:
        return cached

    src = await get_work_item(session, from_id, ctx)
    dst = await get_work_item(session, to_id, ctx)

    adjacency: dict[UUID, list[tuple[UUID, EdgeRecord]]] = {}

    async def edges_of(node_id: UUID) -> list[tuple[UUID, EdgeRecord]]:
        if node_id in adjacency:
            return adjacency[node_id]
        records = await _load_real_edges(session, {node_id})
        if include_virtual:
            records += await _virtual_edges(session, {node_id})
        result: list[tuple[UUID, EdgeRecord]] = []
        for record in records:
            other = record.dst_id if record.src_id == node_id else record.src_id
            if other != node_id:
                result.append((other, record))
        adjacency[node_id] = result
        return result

    if from_id == to_id:
        result = PathRead(
            from_id=from_id, to_id=to_id, exists=True, nodes=[_node_read(src)], edges=[]
        )
        graph_cache.set(key, result)
        return result

    parent: dict[UUID, tuple[UUID, EdgeRecord] | None] = {src.id: None}
    seen = {src.id}
    frontier: deque[UUID] = deque([src.id])
    reached = False
    while frontier and not reached:
        current = frontier.popleft()
        for neighbor, record in await edges_of(current):
            if neighbor in seen:
                continue
            seen.add(neighbor)
            parent[neighbor] = (current, record)
            if neighbor == dst.id:
                reached = True
                break
            frontier.append(neighbor)

    if not reached:
        result = PathRead(from_id=from_id, to_id=to_id, exists=False, nodes=[], edges=[])
        graph_cache.set(key, result)
        return result

    path_records: list[EdgeRecord] = []
    node_id: UUID | None = dst.id
    while node_id is not None:
        entry = parent[node_id]
        if entry is None:
            break
        previous, record = entry
        path_records.append(record)
        node_id = previous
    path_records.reverse()

    nodes: list[WorkItem | User] = [src]
    current_item: WorkItem | User = src
    for record in path_records:
        nxt_id = record.dst_id if record.src_id == current_item.id else record.src_id
        nxt_obj = await _load_node_object(session, nxt_id)
        if nxt_obj is None:
            raise AppError(404, "not_found", "Not found", "Path endpoint is missing.")
        nodes.append(nxt_obj)
        current_item = nxt_obj

    result = PathRead(
        from_id=from_id,
        to_id=to_id,
        exists=True,
        nodes=[_node_read(node) for node in nodes],
        edges=[await _edge_read(session, record) for record in path_records],
    )
    graph_cache.set(key, result)
    return result


def _impact_from_to(record: EdgeRecord) -> tuple[UUID, UUID, Decimal]:
    """Impact edge (from → to, weight) for a ``work_link`` row (plan §7.4)."""
    weight = record.weight or ZERO
    if record.link_type == "depends_on":
        return record.dst_id, record.src_id, weight
    return record.src_id, record.dst_id, weight


async def downstream_impact(
    session: AsyncSession,
    ctx: PermissionContext,
    item_id: UUID,
    max_depth: int = MAX_IMPACT_DEPTH,
) -> DownstreamImpactRead:
    """Affected nodes with min depth and strongest-path weight (plan §7.4)."""
    key = f"impact:{item_id}:{max_depth}"
    cached: DownstreamImpactRead | None = graph_cache.get(key)
    if cached is not None:
        return cached

    root = await get_work_item(session, item_id, ctx)

    # BFS over impact edges in depth waves (cycle-guarded, depth-limited); the same
    # load builds ``in_adj`` (in-edges of discovered nodes).
    depth: dict[UUID, int] = {root.id: 0}
    in_adj: dict[UUID, list[tuple[UUID, Decimal]]] = {}
    frontier: deque[UUID] = deque([root.id])
    while frontier:
        current_depth = depth[frontier[0]]
        if current_depth >= max_depth:
            break
        wave: list[UUID] = []
        while frontier and depth[frontier[0]] == current_depth:
            wave.append(frontier.popleft())
        wave_set = set(wave)
        for record in await _load_real_edges(session, wave_set, link_types=IMPACT_LINK_TYPES):
            from_id, to_id, weight = _impact_from_to(record)
            in_adj.setdefault(to_id, []).append((from_id, weight))
            if from_id in wave_set and to_id not in depth:
                depth[to_id] = current_depth + 1
                frontier.append(to_id)

    impacted_ids = [node_id for node_id in depth if node_id != root.id]

    # Bellman-Ford-style DP (plan §7.4): strongest[v] = max product of weights over
    # simple paths of length ≤ max_depth; depth[v] comes from the BFS above.
    cur: dict[UUID, Decimal] = {root.id: IMPACT_ONE}
    for _ in range(max_depth):
        nxt = dict(cur)
        changed = False
        for node_id in sorted(impacted_ids, key=lambda n: depth[n]):
            candidates = [cur[u] * w for u, w in in_adj.get(node_id, []) if u in cur]
            if candidates:
                candidate = max(candidates)
                if node_id not in nxt or candidate > nxt[node_id]:
                    nxt[node_id] = candidate
                    changed = True
        cur = nxt
        if not changed:
            break

    items_by_id = await _load_items(session, set(impacted_ids))
    impacts = [
        ImpactItemRead(
            id=node_id,
            type=items_by_id[node_id].type,
            title=items_by_id[node_id].title,
            depth=depth[node_id],
            strongest_path_weight=cur.get(node_id),
        )
        for node_id in impacted_ids
        if node_id in items_by_id
    ]
    impacts.sort(key=lambda item: (item.depth, -(item.strongest_path_weight or ZERO)))

    result = DownstreamImpactRead(root_id=root.id, items=impacts)
    graph_cache.set(key, result)
    return result
