"""Performance smoke — plan Phase 9, T9.3.

Single-request latency smoke against the plan's NFR targets (plan §14):

- Interactive API latency: p95 < 400 ms for CRUD/list endpoints
- Dashboard load: < 2 s to first meaningful content
- Capacity recompute: < 5 s (500 resources x 52 weeks at scale; smoke here
  measures the heatmap endpoint against the seeded demo data)

These are timing assertions, not statistical benchmarks — run with
``pytest tests/test_perf_smoke.py -q``.
"""

from __future__ import annotations

import time

from httpx import AsyncClient

CRUD_LATENCY_LIMIT_S = 0.4
DASHBOARD_LIMIT_S = 2.0


def _elapsed_after(start: float) -> float:
    return time.perf_counter() - start


async def test_healthz_fast(client: AsyncClient) -> None:
    start = time.perf_counter()
    response = await client.get("/healthz")
    elapsed = _elapsed_after(start)
    assert response.status_code == 200
    assert elapsed < 0.1


async def test_executive_summary_under_2s(client: AsyncClient, auth) -> None:
    headers = await auth("executive")
    start = time.perf_counter()
    response = await client.get("/api/v1/metrics/summary", headers=headers)
    elapsed = _elapsed_after(start)
    assert response.status_code == 200
    assert elapsed < DASHBOARD_LIMIT_S


async def test_risk_radar_under_1s(client: AsyncClient, auth) -> None:
    # Executive read model (plan §9.5): first call builds the graph via the
    # per-item `downstream_impact` cache; cached calls are expected under 400ms.
    headers = await auth("executive")
    start = time.perf_counter()
    response = await client.get("/api/v1/risk/radar", headers=headers)
    elapsed = _elapsed_after(start)
    assert response.status_code == 200
    assert elapsed < 1.0


async def test_capacity_heatmap_under_400ms(client: AsyncClient, auth) -> None:
    headers = await auth("resource_manager")
    start = time.perf_counter()
    response = await client.get("/api/v1/capacity/heatmap", headers=headers)
    elapsed = _elapsed_after(start)
    assert response.status_code == 200
    assert elapsed < CRUD_LATENCY_LIMIT_S


async def test_prioritization_board_under_1s(client: AsyncClient, auth) -> None:
    # Board endpoint (plan §9.1): first call seeds the default scoring model;
    # cached follow-up calls are expected under 400 ms.
    headers = await auth("portfolio_manager")
    start = time.perf_counter()
    response = await client.get("/api/v1/prioritization", headers=headers)
    elapsed = _elapsed_after(start)
    assert response.status_code == 200
    assert elapsed < 1.0
