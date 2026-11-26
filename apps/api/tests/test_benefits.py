"""Benefit measurement and realisation."""

from __future__ import annotations

from decimal import Decimal

from httpx import AsyncClient


async def _post(client: AsyncClient, headers: dict[str, str], **payload) -> dict:
    response = await client.post("/api/v1/items", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def test_benefit_measurements_and_realisation(client: AsyncClient, auth) -> None:
    pm = await auth("project_manager")
    benefit = await _post(client, pm, type="benefit", title="Annualised savings")

    first = await client.post(
        f"/api/v1/items/{benefit['id']}/benefit-measurements",
        json={
            "period": "2026-01-31",
            "baseline": "100000",
            "target": "200000",
            "actual": "150000",
        },
        headers=pm,
    )
    assert first.status_code == 201, first.text

    duplicate = await client.post(
        f"/api/v1/items/{benefit['id']}/benefit-measurements",
        json={"period": "2026-01-31", "actual": "160000"},
        headers=pm,
    )
    assert duplicate.status_code == 409

    second = await client.post(
        f"/api/v1/items/{benefit['id']}/benefit-measurements",
        json={"period": "2026-02-28", "forecast": "180000"},
        headers=pm,
    )
    assert second.status_code == 201

    realisation = await client.get(f"/api/v1/items/{benefit['id']}/benefit-realisation", headers=pm)
    assert realisation.status_code == 200, realisation.text
    body = realisation.json()
    assert Decimal(body["baseline"]) == Decimal("100000")
    assert Decimal(body["target"]) == Decimal("200000")
    assert Decimal(body["latest_actual"]) == Decimal("150000")
    assert Decimal(body["latest_forecast"]) == Decimal("180000")
    assert Decimal(body["realisation_pct"]) == Decimal("50")
    assert Decimal(body["forecast_pct"]) == Decimal("80")
    assert len(body["measurements"]) == 2

    updated = await client.patch(
        f"/api/v1/benefit-measurements/{first.json()['id']}",
        json={"actual": "160000"},
        headers=pm,
    )
    assert updated.status_code == 200
    refreshed = await client.get(f"/api/v1/items/{benefit['id']}/benefit-realisation", headers=pm)
    assert Decimal(refreshed.json()["realisation_pct"]) == Decimal("60")

    auditor = await auth("auditor")
    audit = await client.get(f"/api/v1/audit?entity_id={benefit['id']}", headers=auditor)
    actions = {row["action"] for row in audit.json()}
    assert {"benefit.measurement_created", "benefit.measurement_updated"} <= actions
