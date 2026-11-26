"""Predictive execution engine (plan §9.5, Phase 7, T7.1-T7.2).

Schedule network from the work graph (``depends_on`` per plan §7.4); Monte Carlo
with NumPy (deterministic via seed): P50/P80/P90 finish dates, criticality index
and sensitivity per activity; delivery confidence for a committed end date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eil.modules.execution.models import WorkItem, WorkLink, WorkType

DEFAULT_OPTIMISTIC_FACTOR = 0.2
DEFAULT_PESSIMISTIC_FACTOR = 0.4

TRIAGE_TYPES = (WorkType.TASK, WorkType.PROJECT, WorkType.MILESTONE)


@dataclass
class ScheduleNode:
    id: UUID
    title: str
    type: str
    duration_days: int
    predecessors: list[UUID] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    optimistic_factor: float = DEFAULT_OPTIMISTIC_FACTOR
    pessimistic_factor: float = DEFAULT_PESSIMISTIC_FACTOR


@dataclass
class ScheduleNetwork:
    nodes: dict[UUID, ScheduleNode] = field(default_factory=dict)
    order: list[UUID] = field(default_factory=list)

    def finish_times(self, durations: dict[UUID, float]) -> dict[UUID, float]:
        finish: dict[UUID, float] = {}
        for node_id in self.order:
            start = max(
                (finish[p] for p in self.nodes[node_id].predecessors if p in finish), default=0.0
            )
            finish[node_id] = start + durations.get(node_id, 0.0)
        return finish


def _duration(item: WorkItem) -> int:
    if item.planned_start is not None and item.planned_end is not None:
        return max(1, (item.planned_end - item.planned_start).days + 1)
    return 0


def _topological_order(nodes: dict[UUID, ScheduleNode]) -> list[UUID]:
    order: list[UUID] = []
    remaining = set(nodes)
    while remaining:
        ready = {n for n in remaining if all(p not in remaining for p in nodes[n].predecessors)}
        if not ready:
            ready = set(remaining)
        order.extend(sorted(ready, key=str))
        remaining -= ready
    return order


async def build_schedule_network(
    session: AsyncSession, items: list[WorkItem] | None = None
) -> ScheduleNetwork:
    if items is None:
        loaded = (
            (
                await session.execute(
                    select(WorkItem).where(
                        WorkItem.type.in_(TRIAGE_TYPES),
                        WorkItem.status != "completed",
                        WorkItem.status != "cancelled",
                    )
                )
            )
            .scalars()
            .all()
        )
        items = list(loaded)
    nodes = {
        item.id: ScheduleNode(
            id=item.id,
            title=item.title,
            type=str(item.type),
            duration_days=_duration(item),
            attributes=item.attributes or {},
        )
        for item in items
    }
    links = (
        (
            await session.execute(
                select(WorkLink).where(
                    WorkLink.link_type == "depends_on", WorkLink.status == "active"
                )
            )
        )
        .scalars()
        .all()
    )
    for link in links:
        if link.src_id in nodes and link.dst_id in nodes:
            nodes[link.src_id].predecessors.append(link.dst_id)
    network = ScheduleNetwork(nodes=nodes)
    network.order = _topological_order(nodes)
    return network


def critical_path(network: ScheduleNetwork) -> list[UUID]:
    finish = network.finish_times({nid: float(n.duration_days) for nid, n in network.nodes.items()})
    if not finish:
        return []
    current = max(finish, key=lambda k: (finish[k], str(k)))
    path: list[UUID] = []
    while current is not None and len(path) <= len(network.nodes):
        path.append(current)
        preds = network.nodes[current].predecessors
        if not preds or all(p not in finish for p in preds):
            break
        current = max((p for p in preds if p in finish), key=lambda p: finish[p])
    return list(reversed(path))


def sample_durations(
    network: ScheduleNetwork, iterations: int = 10000, seed: int | None = None
) -> dict[UUID, np.ndarray]:
    """Triangular sampling from optimistic/pessimistic factors per node."""
    rng = np.random.default_rng(seed)
    sampled: dict[UUID, np.ndarray] = {}
    for node_id in network.order:
        node = network.nodes[node_id]
        duration = float(node.duration_days)
        attrs = node.attributes
        optimistic_factor = float(attrs.get("optimistic_factor", node.optimistic_factor))
        pessimistic_factor = float(attrs.get("pessimistic_factor", node.pessimistic_factor))
        sampled[node_id] = rng.triangular(
            duration * (1 - optimistic_factor),
            duration,
            duration * (1 + pessimistic_factor),
            size=iterations,
        )
    return sampled


def propagate(
    network: ScheduleNetwork, durations: dict[UUID, np.ndarray], iterations: int
) -> dict[UUID, np.ndarray]:
    finish: dict[UUID, np.ndarray] = {}
    for node_id in network.order:
        node = network.nodes[node_id]
        earliest = np.zeros(iterations)
        for pred in node.predecessors:
            if pred in finish:
                earliest = np.maximum(earliest, finish[pred])
        finish[node_id] = earliest + durations[node_id]
    return finish


def criticality_index(
    network: ScheduleNetwork, finish: dict[UUID, np.ndarray]
) -> dict[UUID, float]:
    """Fraction of iterations where the node is the network-wide critical node."""
    if not network.order:
        return {}
    matrix = np.array([finish[nid] for nid in network.order])
    argmax = matrix.argmax(axis=0)
    return {node_id: float((argmax == index).mean()) for index, node_id in enumerate(network.order)}


def sensitivity(network: ScheduleNetwork, finish: dict[UUID, np.ndarray]) -> dict[UUID, float]:
    """Tornado proxy per activity: standard deviation of its finish across iterations."""
    return {node_id: float(np.std(finish[node_id])) for node_id in network.order}


def run_monte_carlo(
    network: ScheduleNetwork, iterations: int = 10000, seed: int | None = None
) -> dict[str, Any]:
    durations = sample_durations(network, iterations=iterations, seed=seed)
    finish = propagate(network, durations, iterations)
    return {
        "iterations": iterations,
        "p50": {nid: float(np.percentile(finish[nid], 50)) for nid in network.order},
        "p80": {nid: float(np.percentile(finish[nid], 80)) for nid in network.order},
        "p90": {nid: float(np.percentile(finish[nid], 90)) for nid in network.order},
        "criticality_index": criticality_index(network, finish),
        "sensitivity": sensitivity(network, finish),
        "finish": finish,
    }


def delivery_confidence(
    finish: dict[UUID, np.ndarray], item_id: UUID, committed_days: float
) -> Decimal:
    """P(finish <= committed_days) — the delivery confidence of a committed date."""
    values = finish.get(item_id)
    if values is None or len(values) == 0:
        return Decimal("0")
    return Decimal(str(float((values <= committed_days).mean())))
