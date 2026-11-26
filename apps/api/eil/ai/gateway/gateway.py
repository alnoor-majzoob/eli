"""Gateway facade (plan §8): routing, validation+repair, telemetry, startup verify."""

from __future__ import annotations

import time
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from eil.ai.gateway.base import ChatResult, LLMClient
from eil.ai.gateway.cache import ResponseCache
from eil.ai.gateway.client import GroqClient
from eil.ai.gateway.errors import LLMError
from eil.ai.gateway.replay import ReplayClient
from eil.ai.gateway.telemetry import hash_request, record_llm_call
from eil.ai.prompts.registry import PromptSpec
from eil.core.config import Settings, get_settings

OutT = TypeVar("OutT", bound=BaseModel)


class Gateway:
    """Single entry point: ``structured`` with schema validation + one repair call.

    Modes (plan §8.4): ``live`` (GroqClient), ``replay``/``record`` (ReplayClient;
    record writes cassettes).
    """

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self.live = GroqClient(self._settings)
        self.replay = ReplayClient(self._settings)
        self.response_cache = ResponseCache(ttl_seconds=self._settings.llm_cache_ttl_seconds)

    @property
    def mode(self) -> str:
        return self._settings.llm_mode

    def client(self) -> LLMClient:
        return self.live if self._settings.llm_mode == "live" else self.replay

    def startup_verify(self) -> list[str]:
        """App startup hook: returns a list of configuration problems."""
        errors: list[str] = []
        if not self._settings.ai_enabled:
            return errors
        if self._settings.llm_mode == "live" and not self._settings.groq_api_key:
            errors.append("AI enabled in live mode but GROQ_API_KEY is not set")
        return errors

    async def structured(
        self,
        prompt: PromptSpec,
        input_data: dict[str, Any],
        *,
        session: AsyncSession | None = None,
        alias: str = "strong",
        max_repairs: int = 1,
    ) -> OutT:
        """Validate LLM JSON output against ``prompt.output_schema`` with repair."""
        client = self.client()
        response_format = None
        if client.capabilities(alias).json_schema:
            response_format = prompt.json_schema_payload()
        messages = prompt.build_messages(input_data)
        result = await self._chat(
            client, prompt, messages, alias=alias, response_format=response_format, session=session
        )
        for attempt in range(max_repairs + 1):
            try:
                return cast(OutT, prompt.output_schema.model_validate_json(result.content))
            except ValidationError as exc:
                if attempt >= max_repairs:
                    break
                repair = (
                    f"The response failed schema validation:\n{exc}\n"
                    "Return corrected JSON only, no other text."
                )
                messages = [
                    *messages,
                    {"role": "assistant", "content": result.content},
                    {"role": "user", "content": repair},
                ]
                result = await self._chat(
                    client,
                    prompt,
                    messages,
                    alias=alias,
                    response_format=response_format,
                    session=session,
                )
        raise LLMError(
            f"Structured output for '{prompt.stamped()}' failed after {max_repairs} repair(s)"
        )

    async def _chat(
        self,
        client: LLMClient,
        prompt: PromptSpec,
        messages: list[dict[str, str]],
        *,
        alias: str,
        response_format: dict[str, Any] | None,
        session: AsyncSession | None,
    ) -> ChatResult:
        model_id = client.model_id(alias)
        request_hash = hash_request(messages, model_id)
        cached = self.response_cache.get(request_hash)
        if cached is not None:
            return ChatResult(content=cached, model_id=model_id, usage={})

        started = time.monotonic()
        try:
            result = await client.chat(
                messages,
                alias=alias,
                temperature=0.0,
                response_format=response_format,
            )
        except Exception as exc:
            if session is not None:
                await record_llm_call(
                    session,
                    purpose=prompt.name,
                    model_alias=alias,
                    model_id=model_id,
                    prompt_version=prompt.telemetry_version(),
                    request_hash=request_hash,
                    status="failed",
                )
            raise LLMError(f"LLM call for '{prompt.stamped()}' failed: {exc}") from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        self.response_cache.set(request_hash, result.content)
        if session is not None:
            await record_llm_call(
                session,
                purpose=prompt.name,
                model_alias=alias,
                model_id=result.model_id,
                prompt_version=prompt.telemetry_version(),
                request_hash=request_hash,
                status="ok",
                input_tokens=result.usage.get("prompt_tokens"),
                output_tokens=result.usage.get("completion_tokens"),
                latency_ms=latency_ms,
            )
        return result


gateway = Gateway()


def get_gateway() -> Gateway:
    return gateway
