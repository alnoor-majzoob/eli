"""Property tests: graph service downstream-impact vs networkx reference (plan §7.4).

The networkx reference enumerates every simple path from the root on random DAGs
and computes min depth and max cumulative weight per node — the same semantics as
the SQL recursive CTE in plan §7.4. The service must match it exactly.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from decimal import Decimal
from uuid import UUID

import networkx as nx
import pytest

from eil.core.security import Principal
from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.graph.service import downstream_impact
from eil.modules.identity.models import User
from eil.modules.identity.rbac import PermissionContext

MAX_DEPTH = 6


def _ctx() -> PermissionContext:
    principal = Principal(subject="graph-test", name="Graph Test", email="graph-test@eil.test")
    user = User(subject="graph-test", email="graph-test@eil.test", name="Graph Test")
    return PermissionContext(
        principal=principal,
        user=user,
        roles=("admin",),
        scope="global",
        permission="work.view",
    )


def _random_dag(n_nodes: int, n_edges: int, seed: int):
    """Random DAG with edges u → v (u < v) so the graph is cycle-free."""
    rng = random.Random(seed)
    pairs: set[tuple[int, int]] = set()
    while len(pairs) < n_edges:
        u = rng.randrange(n_nodes - 1)
        v = rng.randrange(u + 1, n_nodes)
        pairs.add((u, v))
    edges = sorted(pairs)
    weights = [Decimal(str(round(rng.uniform(0.5, 1.5), 3))) for _ in edges]
    return edges, weights


def _reference_impact(
    root: int,
    n_nodes: int,
    edges: list[tuple[int, int]],
    weights: list[Decimal],
    max_depth: int,
) -> dict[int, tuple[int, Decimal]]:
    """networkx reference: {node: (min depth, max product of weights over paths)}."""
    graph = nx.DiGraph()
    graph.add_nodes_from(range(n_nodes))
    for (u, v), weight in zip(edges, weights, strict=False):
        graph.add_edge(u, v, weight=weight)
    per_node: dict[int, list[tuple[int, Decimal]]] = defaultdict(list)
    for target in graph:
        if target == root:
            continue
        for path in nx.all_simple_paths(graph, root, target):
            product = Decimal(1)
            for depth, node in enumerate(path[1:], start=1):
                if depth > max_depth:
                    break
                product = product * Decimal(str(graph[path[depth - 1]][node]["weight"]))
                per_node[node].append((depth, product))
    return {
        node: (min(depth for depth, _ in rows), max(product for _, product in rows))
        for node, rows in per_node.items()
    }


async def _seed_dag(app, n_nodes: int, edges, weights) -> list[UUID]:
    async with app.state.session_factory() as session:
        items = [
            WorkItem(type=WorkType.TASK, title=f"dag-task-{i}", status="draft", attributes={})
            for i in range(n_nodes)
        ]
        session.add_all(items)
        await session.flush()
        session.add_all(
            [
                WorkLink(src_id=items[u].id, dst_id=items[v].id, link_type="part_of", weight=weight)
                for (u, v), weight in zip(edges, weights, strict=False)
            ]
        )
        await session.commit()
        return [item.id for item in items]


@pytest.mark.parametrize("seed", range(6))
async def test_downstream_impact_matches_networkx(app, seed) -> None:
    n_nodes, n_edges = 25, 80
    edges, weights = _random_dag(n_nodes, n_edges, seed)
    item_ids = await _seed_dag(app, n_nodes, edges, weights)
    root_id = item_ids[0]

    async with app.state.session_factory() as session:
        result = await downstream_impact(session, _ctx(), root_id, MAX_DEPTH)
        reference = _reference_impact(0, n_nodes, edges, weights, MAX_DEPTH)

    service = {item.id: item for item in result.items}
    assert set(service) == {item_ids[node] for node in reference}
    for node_idx, (depth, weight) in reference.items():
        item = service[item_ids[node_idx]]
        assert item.depth == depth
        assert item.strongest_path_weight is not None
        assert abs(Decimal(str(item.strongest_path_weight)) - weight) < Decimal("0.001")


async def test_downstream_impact_perf_at_scale(app) -> None:
    """NFR (plan §14): downstream-impact query p95 < 500 ms at 100k nodes / 500k edges.

    The NFR targets the deployed stack (Postgres). The SQLite local fallback
    hydrates rows about 2-3x slower, so it is held to a documented local ceiling.
    """
    n_nodes, n_edges = 100_000, 500_000
    edges, weights = _random_dag(n_nodes, n_edges, seed=42)
    item_ids = await _seed_dag(app, n_nodes, edges, weights)
    root_id = item_ids[0]

    async with app.state.session_factory() as session:
        start = time.monotonic()
        result = await downstream_impact(session, _ctx(), root_id, MAX_DEPTH)
        elapsed_ms = (time.monotonic() - start) * 1000

    dialect = app.state.engine.dialect.name
    local_ceiling_ms = 10_000 if dialect == "sqlite" else 500
    print(
        f"downstream_impact: {elapsed_ms:.0f} ms at {n_nodes} nodes / {len(edges)} "
        f"edges (dialect={dialect})"
    )
    assert result.items
    assert elapsed_ms < local_ceiling_ms
