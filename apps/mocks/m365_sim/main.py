"""m365-sim — Microsoft 365 Graph-shaped simulator (plan §10, Phase 3, T3.3).

Endpoints: GET /health, GET /events?after=, POST /events (admin inject),
POST /webhook-targets (register webhook target).
"""

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, Query  # noqa: E402

from common import EventStore  # noqa: E402

app = FastAPI(title="m365-sim", version="0.1.0")

SEED: list[dict[str, Any]] = [
    {
        "type": "meeting",
        "id": "meeting-001",
        "subject": "HSSE weekly review",
        "organizer": "aisha@example.invalid",
        "attendees": ["mariam@example.invalid", "yousuf@example.invalid"],
        "start": "2026-10-21T09:00:00Z",
        "end": "2026-10-21T09:30:00Z",
        "joinUrl": "https://teams.example.invalid/meet/hsse-weekly",
    },
    {
        "type": "meeting",
        "id": "meeting-002",
        "subject": "Digital transformation steering",
        "organizer": "mariam@example.invalid",
        "attendees": ["ahmed@example.invalid"],
        "start": "2026-10-22T15:00:00Z",
        "end": "2026-10-22T16:00:00Z",
    },
    {
        "type": "message",
        "id": "msg-001",
        "from": "Vendor Ops <ops@example.invalid>",
        "subject": "Delayed consignment",
        "body": "The cargo was delayed at the port; expected to arrive Monday.",
        "receivedDateTime": "2026-10-20T11:30:00Z",
    },
    {
        "type": "message",
        "id": "msg-002",
        "from": "Ahmed Al-Mamari <ahmed@example.invalid>",
        "subject": "Safety helmet shipment",
        "body": "Helmets arrive with the morning delivery.",
        "receivedDateTime": "2026-10-21T08:00:00Z",
    },
    {
        "type": "document",
        "id": "doc-001",
        "name": "Q3 HSSE report",
        "webUrl": "https://sharepoint.example.invalid/hsse/q3-report",
        "path": "/sites/hsse/Q3-HSSE-report.docx",
        "size": 245000,
        "description": "Quarterly HSSE summary.",
    },
    {
        "type": "document",
        "id": "doc-002",
        "name": "Site safety plan",
        "webUrl": "https://sharepoint.example.invalid/hsse/site-plan",
        "path": "/sites/hsse/SiteSafetyPlan.pdf",
        "size": 128000,
        "description": "Annual site safety plan.",
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

    uvicorn.run(app, host="0.0.0.0", port=9105)
