"""eam-sim — Maximo/SAP-PM-shaped simulator (plan §10, Phase 3, T3.3).

Endpoints: GET /health, GET /events?after=, POST /events (admin inject),
POST /webhook-targets (register webhook target).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Query  # noqa: E402

from common import EventStore  # noqa: E402

app = FastAPI(title="eam-sim", version="0.1.0")

SEED: list[dict[str, Any]] = [
    {
        "type": "work_order",
        "work_order_number": "WO-1021",
        "description": "Replace failed pump assembly on Line 3",
        "status": "Open",
        "asset_id": "ASSET-304",
        "due_date": "2026-10-31",
        "priority": "High",
        "notes": "Repair leak on pump P-9."
    },
    {
        "type": "work_order",
        "work_order_number": "WO-1022",
        "description": "Inspect fire suppression system annually",
        "status": "Scheduled",
        "asset_id": "ASSET-100",
        "due_date": "2026-11-15",
        "priority": "Medium",
        "notes": "Engine room system."
    },
    {
        "type": "work_order",
        "work_order_number": "WO-1023",
        "description": "Upgrade safety interlocks on Panel 7",
        "status": "Open",
        "asset_id": "ASSET-412",
        "due_date": "2026-10-20",
        "priority": "High",
        "notes": "Safety-critical interlock upgrade."
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

    uvicorn.run(app, host="0.0.0.0", port=9102)
