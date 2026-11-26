"""erp-sim — ERP simulator (plan §10, Phase 3, T3.3).

Endpoints: GET /health, GET /events?after=, POST /events (admin inject),
POST /webhook-targets (register webhook target).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Query  # noqa: E402

from common import EventStore  # noqa: E402

app = FastAPI(title="erp-sim", version="0.1.0")

SEED: list[dict[str, Any]] = [
    {
        "type": "cost_centre",
        "cost_center_code": "CC-1000",
        "name": "Engineering",
        "description": "Engineering directorate."
    },
    {
        "type": "cost_centre",
        "cost_center_code": "CC-2000",
        "name": "Operations",
        "description": "Operations directorate."
    },
    {
        "type": "purchase_order",
        "po_number": "PO-8041",
        "description": "Cable trays and enclosures",
        "order_date": "2026-10-01",
        "amount": 48000
    },
    {
        "type": "purchase_order",
        "po_number": "PO-8042",
        "description": "Safety helmets and high-vis vests",
        "order_date": "2026-10-05",
        "amount": 12000
    },
    {
        "type": "budget",
        "budget_id": "BUD-5001",
        "budget_name": "Capital equipment Q4 2026",
        "amount": 250000
    },
]

store = EventStore(SEED)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "events": len(store.list_events())}


@app.get("/events")
def list_events(after: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return store.list_events(after)


@app.post("/events", status_code=201)
def inject(payload: dict[str, Any]) -> dict[str, Any]:
    event = store.inject(payload.get("record") or payload)
    return {"event_id": event["id"], "event": event}


@app.post("/webhook-targets")
def add_webhook_target(payload: dict[str, str]) -> dict[str, list[str]]:
    store.add_target(payload["url"])
    return {"targets": store.targets()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9103)
