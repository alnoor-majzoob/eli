"""hr-sim — HR simulator (plan §10, Phase 3, T3.3).

Endpoints: GET /health, GET /events?after=, POST /events (admin inject),
POST /webhook-targets (register webhook target).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Query  # noqa: E402

from common import EventStore  # noqa: E402

app = FastAPI(title="hr-sim", version="0.1.0")

SEED: list[dict[str, Any]] = [
    {
        "type": "employee",
        "employee_id": "E-104",
        "name": "Mariam Al-Habsi",
        "email": "mariam@example.invalid",
        "job_title": "Resource Manager",
        "department": "Portfolio Management Office"
    },
    {
        "type": "employee",
        "employee_id": "E-107",
        "name": "Aisha Al-Zadjali",
        "email": "aisha@example.invalid",
        "job_title": "Project Manager",
        "department": "Projects"
    },
    {
        "type": "certification",
        "certification_id": "CERT-301",
        "certification_name": "ISO 14001 Lead Auditor",
        "issuer": "BSI",
        "expiry_date": "2027-06-30",
        "holder": "Mariam Al-Habsi"
    },
    {
        "type": "leave",
        "leave_id": "L-001",
        "leave_type": "Annual leave",
        "start_date": "2026-11-01",
        "end_date": "2026-11-07"
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

    uvicorn.run(app, host="0.0.0.0", port=9104)
