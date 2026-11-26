"""p6-sim — Primavera P6-shaped simulator (plan §10, Phase 3, T3.3).

Endpoints:
  GET /health
  GET /events?after=<event_id>   — event list (cursor = last event id, "e0000" default)
  POST /events                   — admin "inject event": {"record": {...}} → {"event_id", "event"}
  POST /webhook-targets          — register a webhook target URL (pushed per event)
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Query  # noqa: E402

from common import EventStore  # noqa: E402

app = FastAPI(title="p6-sim", version="0.1.0")

SEED: list[dict[str, Any]] = [
    {
        "type": "activity",
        "activity_code": "A-101",
        "activity_name": "Activate HSSE standards",
        "activity_description": "Deploy the new HSSE manual across the site.",
        "activity_status": "Complete",
        "start_date": "2026-10-01",
        "finish_date": "2026-10-05",
        "duration": 5,
    },
    {
        "type": "activity",
        "activity_code": "A-102",
        "activity_name": "Inspect pressure vessels",
        "activity_description": "Monthly integrity inspection of vessels.",
        "activity_status": "In progress",
        "start_date": "2026-10-02",
        "finish_date": "2026-10-09",
        "duration": 8,
    },
    {
        "type": "activity",
        "activity_code": "A-103",
        "activity_name": "Train crew on emergency procedures",
        "activity_description": "Conduct emergency-procedures drills.",
        "activity_status": "Scheduled",
        "start_date": "2026-10-10",
        "finish_date": "2026-10-12",
    },
    {
        "type": "milestone",
        "milestone_code": "M-201",
        "milestone_name": "Pressure vessel inspection due",
        "baseline_finish": "2026-10-09",
        "milestone_description": "Vessels must be inspected by the due date.",
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

    uvicorn.run(app, host="0.0.0.0", port=9101)
