"""Configurable taxonomy for classification (plan §8.6, §8.7)."""

from __future__ import annotations

import json

TAXONOMY: dict[str, list[str]] = {
    "types": [
        "task",
        "commitment",
        "risk",
        "decision",
        "milestone",
        "project",
        "program",
        "objective",
    ],
    "categories": [
        "administration",
        "engineering",
        "hsse",
        "finance",
        "procurement",
        "operations",
        "strategy",
        "it",
    ],
    "departments": ["pmo", "projects", "maintenance", "engineering", "hsse", "it", "exec", "ops"],
    "regulatory": ["iso_14001", "iso_45001", "osha", "seveso"],
}


def taxonomy_json() -> str:
    return json.dumps(TAXONOMY, ensure_ascii=False, indent=1)
