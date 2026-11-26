"""Groq live client (plan §8.1, §8.4): retry/backoff, rate limits, circuit breaker."""

from __future__ import annotations

import asyncio
import json
import random
from collections import defaultdict
from typing import Any

import httpx

from eil.ai.gateway.base import ChatResult, LLMCapabilities, ToolCall
from eil.ai.gateway.circuit_breaker import CircuitBreaker
from eil.ai.gateway.errors import LLMError
from eil.ai.gateway.limiter import TokenBucket
from eil.core.config import Settings, get_settings

_MODEL_CONTEXTS: dict[str, int] = {
    "llama-3.1-8b-instant": 8192,
    "llama-3.3-70b-versatile": 131072,
    "openai/gpt-oss-120b": 131072,
}


class GroqClient:
    """OpenAI-compatible chat client against the Groq API."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or get_settings()
        self._api_key = self._settings.groq_api_key
        self._http = httpx.AsyncClient(base_url=self._settings.groq_base_url, timeout=60.0)
        self._breakers: dict[str, CircuitBreaker] = defaultdict(CircuitBreaker)
        self._limiters: dict[str, TokenBucket] = {}
        self._models: dict[str, str] = {
            "fast": self._settings.model_fast,
            "strong": self._settings.model_strong,
            "stt": self._settings.model_stt,
        }

    def capabilities(self, alias: str) -> LLMCapabilities:
        return LLMCapabilities(
            json_schema=True,
            tools=True,
            streaming=True,
            max_context=_MODEL_CONTEXTS.get(self._model_id(alias), 131072),
        )

    def model_id(self, alias: str) -> str:
        return self._model_id(alias)

    def _model_id(self, alias: str) -> str:
        return self._models.get(alias, alias) or self._settings.model_fast

    def _limiter(self, alias: str) -> TokenBucket:
        limiter = self._limiters.get(alias)
        if limiter is None:
            settings = self._settings
            rpm = {
                "fast": settings.llm_rpm_fast,
                "strong": settings.llm_rpm_strong,
            }.get(alias, settings.llm_rpm_stt or 10)
            limiter = TokenBucket(rpm, rpm)
            self._limiters[alias] = limiter
        return limiter

    async def _call(
        self,
        messages: list[dict[str, str]],
        *,
        alias: str,
        temperature: float,
        max_tokens: int | None,
        response_format: dict[str, Any] | None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResult:
        model_id = self._model_id(alias)
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": response_format}
        if tools is not None:
            payload["tools"] = tools

        attempts = 0
        while True:
            attempts += 1
            await self._limiter(alias).acquire(1)
            breaker = self._breakers[alias]
            if breaker.is_open():
                raise LLMError(f"Circuit breaker open for '{alias}'")
            try:
                response = await self._http.post(
                    "/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                breaker.record_failure()
                retry_after = exc.response.headers.get("retry-after")
                if retry_after:
                    await asyncio.sleep(float(retry_after))
                if attempts >= self._settings.llm_max_retries:
                    raise
                await asyncio.sleep(min(2**attempts, 10) + random.random())
                continue
            except httpx.HTTPError:
                breaker.record_failure()
                if attempts >= self._settings.llm_max_retries:
                    raise
                await asyncio.sleep(min(2**attempts, 10) + random.random())
                continue
            breaker.record_success()
            data = response.json()
            choices = data.get("choices") or [{}]
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            tool_calls = [
                ToolCall(
                    id=call.get("id") or f"call_{index}",
                    name=(call.get("function") or {}).get("name") or "",
                    arguments=json.loads((call.get("function") or {}).get("arguments") or "{}"),
                )
                for index, call in enumerate(message.get("tool_calls") or [])
            ]
            usage = data.get("usage") or {}
            return ChatResult(
                content=content,
                model_id=data.get("model") or model_id,
                usage={
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
                tool_calls=tool_calls,
            )

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
        return await self._call(
            messages,
            alias=alias,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            tools=tools,
        )
