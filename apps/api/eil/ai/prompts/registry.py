"""Prompt registry (plan §8.5): YAML prompts, content-hash stamping.

Prompts live in ``eil/ai/prompts/v1/<name>.yaml``:
```yaml
name: detect_candidates
version: v1
system: |
  ...
user: |
  ... {{artifact_text}}
schema: {type: object, ...}
```
Every ``llm_call`` and ``ai_suggestion`` carries ``<name>@v1+<hash>`` as the
prompt version.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from eil.ai.schemas import (
    AdjudicateDuplicateOutput,
    ClassifyItemOutput,
    DetectCandidatesOutput,
    OwnerSuggestionOutput,
    RerankLinksOutput,
    ScoreAssistOutput,
    StructuredItemsOutput,
)

PROMPTS_DIR = Path(__file__).parent / "v1"


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: str
    system: str
    user_template: str
    schema: dict[str, Any]
    output_schema: Any
    input_fields: tuple[str, ...]

    def stamped(self) -> str:
        return f"{self.name}@{self.version}"

    def hash(self) -> str:
        payload = json.dumps(
            {
                "name": self.name,
                "version": self.version,
                "system": self.system,
                "user": self.user_template,
                "schema": self.schema,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def telemetry_version(self) -> str:
        return f"{self.stamped()}+{self.hash()[:12]}"

    def json_schema_payload(self) -> dict[str, Any]:
        return {"name": self.stamped(), "schema": self.schema, "strict": True}

    def build_messages(self, input_data: dict[str, Any]) -> list[dict[str, str]]:
        user = re.sub(
            r"\{\{\s*(\w+)\s*\}\}",
            lambda match: str(input_data.get(match.group(1), "")),
            self.user_template,
        )
        return [{"role": "system", "content": self.system}, {"role": "user", "content": user}]


class PromptRegistry:
    def __init__(self, base_dir: Path | None = None):
        self._dir = base_dir or PROMPTS_DIR
        self._specs: dict[str, PromptSpec] = {}
        for path in sorted(self._dir.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            name = raw["name"]
            output_models = {
                "detect_candidates": DetectCandidatesOutput,
                "structure_items": StructuredItemsOutput,
                "classify_item": ClassifyItemOutput,
                "adjudicate_duplicate": AdjudicateDuplicateOutput,
                "rerank_links": RerankLinksOutput,
                "detect_owner_hint": OwnerSuggestionOutput,
                "score_assist": ScoreAssistOutput,
            }
            spec = PromptSpec(
                name=name,
                version=str(raw.get("version", "v1")),
                system=str(raw.get("system", "")),
                user_template=str(raw.get("user", "")),
                schema=raw.get("schema") or {},
                output_schema=output_models[name],
                input_fields=tuple(raw.get("input_fields", [])),
            )
            self._specs[name] = spec

    def get(self, name: str, version: str = "v1") -> PromptSpec:
        spec = self._specs.get(name)
        if spec is None or spec.version != version:
            raise KeyError(f"Unknown prompt: {name}@{version}")
        return spec

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))


prompt_registry = PromptRegistry()
