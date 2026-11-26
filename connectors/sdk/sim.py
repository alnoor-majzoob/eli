"""HTTP helpers for simulator-backed connectors (plan §10, Phase 3, T3.3).

Simulators (``apps/mocks/*_sim``) expose ``GET /events?after=`` and
``POST /events`` (admin inject). Connectors in ``sim`` mode pull from the sim;
in ``live`` mode they raise ``NotSupportedError`` (skeletons per plan §10, T3.4).
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from connectors.sdk.urls import validate_connector_url

_SIM_PORTS: dict[str, int] = {
    "p6": 9101,
    "eam": 9102,
    "erp": 9103,
    "hr": 9104,
    "m365": 9105,
}


def _validate_sim_url(base_url: str) -> str:
    # Simulators run on the local/LAN network by design; validate shape and
    # credentials only (SSRF rules, plan §13.3, Phase 9, T9.2).
    return validate_connector_url(base_url, allow_private=True, require_https=False)


def sim_base(system: str) -> str:
    base = os.environ.get(
        f"{system.upper()}_SIM_URL", f"http://localhost:{_SIM_PORTS[system]}"
    ).rstrip("/")
    return _validate_sim_url(base)


def fetch_events(base_url: str, since_cursor: str | None = None) -> list[dict[str, Any]]:
    _validate_sim_url(base_url)
    url = f"{base_url}/events"
    if since_cursor:
        url += f"?after={since_cursor}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def post_event(base_url: str, record: dict[str, Any], timeout: float = 5.0) -> dict[str, Any]:
    _validate_sim_url(base_url)
    request = urllib.request.Request(
        f"{base_url}/events",
        data=json.dumps({"record": record}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)
