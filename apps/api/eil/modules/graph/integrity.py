"""Graph integrity checks: depends_on cycles, orphan tasks, duplicate edges.

- Cycle detection on ``depends_on``: insert-time rejection lives in
  ``execution.service.create_work_link``; this report lists any existing cycles.
- Orphan report: tasks whose connected component (via ``aligns_to``/``part_of``)
  has no ``objective`` — i.e. no aligns_to path to an objective.
- Duplicate-edge prevention: ``work_link.uq_work_link_edge`` plus the service
  check; reported here defensively.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.graph.schemas import (
    GraphIntegrityRead,
    IntegrityCycleRead,
    IntegrityDuplicateEdgeRead,
    IntegrityOrphanRead,
)
from eil.modules.graph.service import _load_items, _load_real_edges, _node_read

ORPHAN_REASON = "No aligns_to path to an objective."

_ORPHAN_LINK_TYPES = ("aligns_to", "part_of")
_CYCLE_LINK_TYPES = ("depends_on",)


class _DisjointSet:
    """Minimal union-find used for the orphan-task component analysis."""

    def __init__(self) -> None:
        self._parent: dict[UUID, UUID] = {}

    def add(self, node: UUID) -> None:
        self._parent.setdefault(node, node)

    def find(self, node: UUID) -> UUID:
        self.add(node)
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[node] != root:
            self._parent[node], node = root, self._parent[node]
        return root

    def union(self, a: UUID, b: UUID) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b


def _find_cycles(adj: dict[UUID, list[UUID]], titles: dict[UUID, str]) -> list[list[UUID]]:
    """Iterative DFS over ``adj`` (src → [dst]) returning one node list per back edge."""
    color: dict[UUID, int] = {}
    cycles: list[list[UUID]] = []
    for start in sorted(adj, key=lambda n: titles.get(n, "")):
        if color.get(start, 0) != 0:
            continue
        color[start] = 1
        path: list[UUID] = [start]
        stack: list[tuple[UUID, list[UUID], int]] = [(start, adj.get(start, []), 0)]
        while stack:
            node, successors, index = stack[-1]
            if index >= len(successors):
                color[node] = 2
                stack.pop()
                path.pop()
                continue
            stack[-1] = (node, successors, index + 1)
            neighbor = successors[index]
            if color.get(neighbor, 0) == 0:
                color[neighbor] = 1
                path.append(neighbor)
                stack.append((neighbor, adj.get(neighbor, []), 0))
            elif color.get(neighbor, 0) == 1 and neighbor in path:
                cycles.append(path[path.index(neighbor) :])
    unique: list[list[UUID]] = []
    seen: set[frozenset[UUID]] = set()
    for cycle in cycles:
        key = frozenset(cycle)
        if key not in seen:
            seen.add(key)
            unique.append(cycle)
    return unique


async def find_depends_on_cycles(
    session: AsyncSession, max_cycles: int = 50
) -> list[IntegrityCycleRead]:
    """List cycles in the active ``depends_on`` subgraph (Plan §7.3 integrity rules)."""
    records = await _load_real_edges(session, set(), link_types=_CYCLE_LINK_TYPES)
    adj: dict[UUID, list[UUID]] = {}
    for record in records:
        adj.setdefault(record.src_id, []).append(record.dst_id)
    items = await _load_items(session, set(adj))
    titles = {item_id: item.title for item_id, item in items.items()}
    result = []
    for cycle_nodes in _find_cycles(adj, titles)[:max_cycles]:
        nodes = [items[node_id] for node_id in cycle_nodes if node_id in items]
        if not nodes:
            continue
        result.append(IntegrityCycleRead(nodes=[_node_read(node) for node in nodes]))
    return result


async def report_orphan_tasks(
    session: AsyncSession, max_orphans: int = 100
) -> list[IntegrityOrphanRead]:
    """Tasks whose component via aligns_to/part_of has no objective."""
    records = await _load_real_edges(session, set(), link_types=_ORPHAN_LINK_TYPES)
    ds = _DisjointSet()
    for record in records:
        ds.add(record.src_id)
        ds.add(record.dst_id)
        ds.union(record.src_id, record.dst_id)

    objectives = list(
        (await session.execute(select(WorkItem.id).where(WorkItem.type == WorkType.OBJECTIVE)))
        .scalars()
        .all()
    )
    objective_roots = {ds.find(objective_id) for objective_id in objectives}

    stmt = (
        select(WorkItem.id, WorkItem.type, WorkItem.title)
        .where(WorkItem.type == WorkType.TASK)
        .limit(max_orphans)
    )
    orphans = []
    for row in (await session.execute(stmt)).all():
        if ds.find(row.id) not in objective_roots:
            orphans.append(
                IntegrityOrphanRead(id=row.id, type=row.type, title=row.title, reason=ORPHAN_REASON)
            )
    return orphans


async def find_duplicate_edges(session: AsyncSession) -> list[IntegrityDuplicateEdgeRead]:
    """Defensive scan for duplicate (src, dst, link_type) edges."""
    rows = (
        await session.execute(
            select(WorkLink.src_id, WorkLink.dst_id, WorkLink.link_type, func.count())
            .group_by(WorkLink.src_id, WorkLink.dst_id, WorkLink.link_type)
            .having(func.count() > 1)
        )
    ).all()
    return [
        IntegrityDuplicateEdgeRead(src_id=row[0], dst_id=row[1], link_type=row[2], count=row[3])
        for row in rows
    ]


async def check_graph_integrity(session: AsyncSession) -> GraphIntegrityRead:
    """Combined integrity report (orphans, depends_on cycles, duplicate edges)."""
    return GraphIntegrityRead(
        orphan_tasks=await report_orphan_tasks(session),
        depends_on_cycles=await find_depends_on_cycles(session),
        duplicate_edges=await find_duplicate_edges(session),
    )


__all__ = [
    "ORPHAN_REASON",
    "check_graph_integrity",
    "find_depends_on_cycles",
    "find_duplicate_edges",
    "report_orphan_tasks",
]
