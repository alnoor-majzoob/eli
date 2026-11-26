"""Connector contract tests (plan §10, Phase 3, T3.3/T4).

Contract per connector: ``capabilities()`` shape, YAML mapping correctness,
sim-mode ``pull`` against the simulator (``m365-sim`` is spawned in-process via
subprocess), ``handle_webhook`` parsing, live-mode skeletons raising, mode
override via ``CONNECTOR_MODE_<SYSTEM>``.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
from connectors.sdk import get_connector, mode_for

REPO_ROOT = Path(__file__).resolve().parents[3]


def _start_sim(sim: str, port: int) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "apps" / "mocks" / sim / "main.py")],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            import urllib.request

            with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=0.5) as response:
                if response.status == 200:
                    return process
        except OSError:
            time.sleep(0.2)
    process.terminate()
    raise AssertionError(f"{sim} did not start within 10 s")


@pytest.mark.parametrize(
    ("system", "record_types"),
    [
        ("p6", ("activity", "milestone")),
        ("eam", ("work_order",)),
        ("erp", ("cost_centre", "purchase_order", "budget")),
        ("hr", ("employee", "certification", "leave")),
        ("m365", ("meeting", "message", "document")),
    ],
)
def test_connector_capabilities(system: str, record_types: tuple[str, ...]) -> None:
    connector = get_connector(system)
    caps = connector.capabilities()
    assert caps.system == system
    assert tuple(caps.record_types) == record_types
    assert "sim" in caps.modes
    assert caps.default_mode == "sim"


def test_m365_pull_against_sim() -> None:
    process = _start_sim("m365_sim", 9105)
    try:
        connector = get_connector("m365")
        records = list(connector.pull("e0000"))
        assert len(records) >= 2
        assert all(record.is_simulated for record in records)
        by_type = {record.canonical_type for record in records}
        assert {"meeting", "message", "document"} <= by_type
        # Mapping: canonical type + mapped fields from the YAML mapping.
        meeting = next(r for r in records if r.canonical_type == "meeting")
        canonical_type, payload = connector.map_payload(meeting)
        assert canonical_type == "meeting"
        assert payload["title"] == "HSSE weekly review"
        assert payload["start_time"].isoformat().startswith("2026-10-21T09:00")
        # Idempotency-friendly cursor: re-pull returns nothing after cursor.
        assert list(connector.pull(records[-1].external_id)) == []
    finally:
        process.terminate()
        process.wait(timeout=5)


SIM_PORTS: dict[str, int] = {
    "p6_sim": 9101,
    "eam_sim": 9102,
    "erp_sim": 9103,
    "hr_sim": 9104,
    "m365_sim": 9105,
}

SIM_SYSTEMS: dict[str, str] = {
    "p6_sim": "p6",
    "eam_sim": "eam",
    "erp_sim": "erp",
    "hr_sim": "hr",
    "m365_sim": "m365",
}


@pytest.mark.parametrize(
    ("sim", "expected_types"),
    [
        ("p6_sim", ("activity", "activity", "activity", "milestone")),
        ("eam_sim", ("work_order", "work_order", "work_order")),
        ("erp_sim", ("cost_centre", "cost_centre", "purchase_order", "purchase_order", "budget")),
        ("hr_sim", ("employee", "employee", "certification", "leave")),
        ("m365_sim", ("meeting", "meeting", "message", "message", "document", "document")),
    ],
)
def test_sim_pull_returns_seeded_events(sim: str, expected_types: tuple[str, ...]) -> None:
    """Plan §10, Phase 3, T3.3 exit: records land in the work graph from every sim."""
    process = _start_sim(sim, SIM_PORTS[sim])
    try:
        connector = get_connector(SIM_SYSTEMS[sim])
        records = list(connector.pull("e0000"))
        assert tuple(record.canonical_type for record in records) == expected_types
        assert all(record.is_simulated for record in records)
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_m365_handle_webhook_parsing() -> None:
    connector = get_connector("m365")
    record = {"id": "meeting-999", "subject": "Webhook meeting", "start": "2026-11-01T10:00:00Z"}
    raws = connector.handle_webhook({"id": "e9001", "type": "meeting", "record": record})
    assert len(raws) == 1
    assert raws[0].external_id == "e9001"
    assert raws[0].canonical_type == "meeting"
    assert raws[0].payload["subject"] == "Webhook meeting"


@pytest.mark.parametrize("system", ["p6", "eam", "erp", "hr"])
def test_live_mode_skeletons_raise(system: str) -> None:
    connector = get_connector(system, "live")
    assert connector.mode == "live"
    with pytest.raises(NotImplementedError):
        connector.authenticate()
    with pytest.raises(NotImplementedError):
        list(connector.pull())


def test_mode_override_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONNECTOR_MODE_P6", "live")
    assert mode_for("p6") == "live"
    monkeypatch.delenv("CONNECTOR_MODE_P6")
    assert mode_for("p6") == "sim"
