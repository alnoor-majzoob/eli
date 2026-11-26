"""Predictive execution engine (plan §9.5, Phase 7, T7.1-T7.2)."""

from __future__ import annotations

from datetime import date, timedelta

from eil.modules.execution.models import WorkItem, WorkLink, WorkType
from eil.modules.risk import engine


def _item(
    title: str,
    start: date,
    end: date,
    item_type: WorkType = WorkType.TASK,
    attributes: dict | None = None,
) -> WorkItem:
    return WorkItem(
        type=item_type,
        title=title,
        status="active",
        planned_start=start,
        planned_end=end,
        attributes=attributes or {},
    )


async def test_build_schedule_network_and_critical_path(app) -> None:
    start = date(2026, 12, 1)
    item_a = _item("Activity A", start, start + timedelta(days=2))
    item_b = _item("Activity B", start + timedelta(days=2), start + timedelta(days=5))
    async with app.state.session_factory() as session:
        session.add_all([item_a, item_b])
        await session.flush()
        session.add(
            WorkLink(
                src_id=item_b.id,
                dst_id=item_a.id,
                link_type="depends_on",
                origin="system",
                status="active",
                weight=1,
            )
        )
        network = await engine.build_schedule_network(session)
        assert item_a.id in network.nodes and item_b.id in network.nodes
        assert item_a.id in network.nodes[item_b.id].predecessors
        path = engine.critical_path(network)
        assert path[-1] == item_b.id
        assert item_a.id in path


async def test_monte_carlo_deterministic_with_seed(app) -> None:
    start = date(2026, 12, 1)
    item = _item("Activity A", start, start + timedelta(days=5))
    async with app.state.session_factory() as session:
        session.add(item)
        await session.flush()
        network = await engine.build_schedule_network(session)
        first = engine.run_monte_carlo(network, iterations=500, seed=7)
        second = engine.run_monte_carlo(network, iterations=500, seed=7)
        assert first["p50"][item.id] == second["p50"][item.id]
        assert 0 < first["p50"][item.id] < 20
        assert set(first["criticality_index"]) == set(network.nodes)
        assert set(first["sensitivity"]) == set(network.nodes)


async def test_delivery_confidence_monotone_in_delay(app) -> None:
    start = date(2026, 12, 1)
    item = _item("Activity A", start, start + timedelta(days=5))
    async with app.state.session_factory() as session:
        session.add(item)
        await session.flush()
        network = await engine.build_schedule_network(session)
        result = engine.run_monte_carlo(network, iterations=2000, seed=3)
        confident = engine.delivery_confidence(result["finish"], item.id, committed_days=10)
        cautious = engine.delivery_confidence(result["finish"], item.id, committed_days=30)
        assert 0.0 <= float(confident) <= float(cautious) <= 1.0
