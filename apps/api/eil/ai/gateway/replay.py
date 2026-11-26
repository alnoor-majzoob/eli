"""Replay mode client (plan §8.4): serves recorded responses for demo/CI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eil.ai.gateway.base import ChatResult, LLMCapabilities
from eil.ai.gateway.errors import ReplayError
from eil.ai.gateway.telemetry import hash_request
from eil.core.config import REPO_ROOT, Settings, get_settings


class ReplayClient:
    """Deterministic client: cassette keyed by request hash.

    Cassette files live in ``<repo>/seed/cassettes/*.json`` with entries
    ``{"key": <sha256>, "response": <str>, "model_id": <str>}``.
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._cassettes: dict[str, dict[str, Any]] = {}
        base = Path(self._settings.replay_cassette_dir)
        if not base.is_absolute():
            base = REPO_ROOT / base
        if base.is_dir():
            for path in sorted(base.glob("*.json")):
                try:
                    entries = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                for entry in entries or []:
                    key = entry.get("key")
                    if key and "response" in entry:
                        self._cassettes[str(key)] = entry

    def register(self, key: str, response: str, model_id: str = "replay") -> None:
        """Register (or override) a cassette — used by tests and CI."""
        self._cassettes[key] = {"key": key, "response": response, "model_id": model_id}

    def capabilities(self, alias: str) -> LLMCapabilities:
        return LLMCapabilities(json_schema=True)

    def model_id(self, alias: str) -> str:
        return self._settings.model_stt if alias == "stt" else "replay"

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        alias: str,
        temperature: float,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        del tools
        key = hash_request(messages, self.model_id(alias))
        entry = self._cassettes.get(key)
        if entry is None:
            raise ReplayError(f"No replay cassette for request hash {key[:12]}…")
        return ChatResult(
            content=entry["response"],
            model_id=str(entry.get("model_id") or self.model_id(alias)),
            usage={},
        )
