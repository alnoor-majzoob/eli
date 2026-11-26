"""LLM gateway (plan §8): GroqClient live path (respx), ReplayClient, gateway
structured-output validation + repair, startup verify, rate limiter, circuit breaker."""

from __future__ import annotations

import json
import time

import httpx
import pytest
import respx

from eil.ai.gateway import CircuitBreaker, Gateway, GroqClient, ReplayClient, TokenBucket
from eil.ai.gateway.errors import LLMError, ReplayError
from eil.ai.gateway.telemetry import hash_request
from eil.ai.prompts.registry import prompt_registry
from eil.ai.schemas import DetectCandidatesOutput
from eil.core.config import Settings


async def test_replay_client_serves_cassette() -> None:
    client = ReplayClient(Settings(llm_mode="replay"))
    messages = [{"role": "user", "content": "hi"}]
    key = hash_request(messages, "replay")
    client.register(key, '{"candidates": []}')
    result = await client.chat(messages, alias="fast", temperature=0.0)
    assert result.content == '{"candidates": []}'
    assert result.model_id == "replay"

    with pytest.raises(ReplayError):
        await client.chat([{"role": "user", "content": "missing"}], alias="fast", temperature=0.0)


async def test_groq_client_request_shape() -> None:
    settings = Settings(llm_mode="live", groq_api_key="gsk-test", model_fast="m-fast")
    client = GroqClient(settings)
    try:
        with respx.mock:
            route = respx.post("https://api.groq.com/openai/v1/chat/completions").respond(
                200,
                json={
                    "model": "m-fast",
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 5},
                },
            )
            result = await client.chat(
                [{"role": "user", "content": "hi"}],
                alias="fast",
                temperature=0.0,
                response_format={"type": "object"},
            )
        assert result.content == '{"ok": true}'
        assert result.model_id == "m-fast"
        assert result.usage == {"prompt_tokens": 3, "completion_tokens": 5}
        request = route.calls[0].request
        assert request.headers["Authorization"] == "Bearer gsk-test"
        payload = json.loads(request.content)
        assert payload["model"] == "m-fast"
        assert payload["response_format"] == {
            "type": "json_object",
            "json_schema": {"type": "object"},
        }
    finally:
        await client._http.aclose()


async def test_groq_client_retries_on_5xx() -> None:
    settings = Settings(llm_mode="live", groq_api_key="gsk-test", llm_max_retries=3)
    client = GroqClient(settings)
    try:
        with respx.mock:
            route = respx.post("https://api.groq.com/openai/v1/chat/completions")
            route.side_effect = [
                httpx.Response(500, json={"error": "boom"}),
                httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
            ]
            result = await client.chat(
                [{"role": "user", "content": "hi"}], alias="fast", temperature=0.0
            )
        assert result.content == "ok"
        assert len(route.calls) == 2
    finally:
        await client._http.aclose()


async def test_groq_client_circuit_breaker_opens() -> None:
    settings = Settings(llm_mode="live", groq_api_key="gsk-test", llm_max_retries=1)
    client = GroqClient(settings)
    client._breakers["fast"] = CircuitBreaker(threshold=1, cooldown_seconds=30)
    try:
        with respx.mock:
            respx.post("https://api.groq.com/openai/v1/chat/completions").respond(
                500, json={"error": "down"}
            )
            with pytest.raises(httpx.HTTPStatusError):
                await client.chat(
                    [{"role": "user", "content": "hi"}], alias="fast", temperature=0.0
                )
            assert client._breakers["fast"].is_open()
            with pytest.raises(LLMError):
                await client.chat(
                    [{"role": "user", "content": "hi"}], alias="fast", temperature=0.0
                )
    finally:
        await client._http.aclose()


async def test_gateway_structured_returns_validated_model() -> None:
    gateway = Gateway(Settings(llm_mode="replay", ai_enabled=True))
    prompt = prompt_registry.get("detect_candidates")
    input_data = {"artifact_text": "Meeting transcript: pump failed."}
    key = hash_request(prompt.build_messages(input_data), gateway.client().model_id("strong"))
    gateway.replay.register(
        key,
        json.dumps(
            {
                "candidates": [
                    {
                        "title": "Replace pump",
                        "kind": "task",
                        "summary": "Replace pump",
                        "evidence_quote": "pump failed",
                    },
                ]
            }
        ),
    )
    result = await gateway.structured(prompt, input_data)
    assert isinstance(result, DetectCandidatesOutput)
    assert result.candidates[0].title == "Replace pump"


async def test_gateway_structured_raises_when_validation_fails() -> None:
    gateway = Gateway(Settings(llm_mode="replay", ai_enabled=True))
    prompt = prompt_registry.get("detect_candidates")
    input_data = {"artifact_text": "Meeting transcript: pump failed."}
    key = hash_request(prompt.build_messages(input_data), gateway.client().model_id("strong"))
    gateway.replay.register(key, json.dumps({"candidates": [{"title": "missing kind and quote"}]}))
    with pytest.raises(LLMError):
        await gateway.structured(prompt, input_data)


def test_gateway_startup_verify() -> None:
    gateway = Gateway(Settings(llm_mode="live", ai_enabled=True, groq_api_key=""))
    assert gateway.startup_verify() == ["AI enabled in live mode but GROQ_API_KEY is not set"]
    gateway = Gateway(Settings(llm_mode="replay", ai_enabled=True))
    assert gateway.startup_verify() == []
    gateway = Gateway(Settings(ai_enabled=False))
    assert gateway.startup_verify() == []


async def test_token_bucket_rate_limits() -> None:
    bucket = TokenBucket(rate_per_min=60, capacity=1)
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    assert time.monotonic() - start >= 0.8


def test_circuit_breaker_opens_after_failures() -> None:
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=30)
    assert not breaker.is_open()
    breaker.record_failure()
    assert not breaker.is_open()
    breaker.record_failure()
    assert breaker.is_open()
    breaker.record_success()
    assert not breaker.is_open()
