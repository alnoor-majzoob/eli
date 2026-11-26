"""AI eval gate (plan §15.3, Phase 4, T4.13).

Runs the deterministic replay scenarios from ``eil/ai/evals/initial.json``:
each cassette is registered against the real prompt (``<name>@v1``) and the
pipeline output is checked. Exits non-zero on failure.

Usage: ``uv run python scripts/ai_evals.py`` (from ``apps/api``).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from eil.ai.gateway import get_gateway
from eil.ai.gateway.telemetry import hash_request
from eil.ai.prompts.registry import prompt_registry

EVALS_FILE = Path(__file__).resolve().parents[1] / "eil" / "ai" / "evals" / "initial.json"


async def run_scenarios() -> int:
    data = json.loads(EVALS_FILE.read_text(encoding="utf-8"))
    gateway = get_gateway()
    failures = 0
    for scenario in data.get("scenarios", []):
        prompt = prompt_registry.get(scenario["prompt"].split("@")[0])
        messages = prompt.build_messages(scenario["input"])
        key = hash_request(messages, gateway.client().model_id("fast"))
        gateway.replay.register(key, json.dumps(scenario["cassette"]))
        try:
            result = await gateway.structured(prompt, scenario["input"])
        except Exception as exc:
            failures += 1
            print(f"FAIL {scenario['name']}: {exc}")
            continue
        text = json.dumps(result.model_dump(mode="json"), default=str)
        expected_items = scenario.get("expect_contains", [])
        missing = [expected for expected in expected_items if expected not in text]
        if missing:
            failures += 1
            print(f"FAIL {scenario['name']}: missing {missing}")
        else:
            print(f"PASS {scenario['name']}")
    return 1 if failures else 0


def main() -> int:
    return asyncio.run(run_scenarios())


if __name__ == "__main__":
    sys.exit(main())
