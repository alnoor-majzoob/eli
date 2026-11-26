"""LLM client protocol shared by live, replay and record modes (plan §8.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from eil.ai.gateway.errors import LLMError


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResult:
    content: str
    model_id: str
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class LLMCapabilities:
    json_schema: bool = True
    tools: bool = False
    streaming: bool = False
    max_context: int = 131072


class LLMClient(Protocol):
    """Minimal chat contract; telemetry, redaction and caching live in the Gateway."""

    def capabilities(self, alias: str) -> LLMCapabilities: ...

    def model_id(self, alias: str) -> str: ...

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        alias: str,
        temperature: float,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult: ...


__all__ = ["ChatResult", "LLMCapabilities", "LLMClient", "LLMError"]
