"""Isoquant's Pipecat adapter and configuration contract."""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from pipecat.processors.aggregators.llm_context import LLMContext
from voice_runtime.contracts.providers import LLMConfig, LLMFallbackConfig
from voice_runtime.execution.isoquant import IsoquantLLMService
from voice_runtime.execution.llm_factory import build_llm_service


def test_isoquant_model_and_effort_are_validated():
    LLMConfig(provider="isoquant", model="glm-5.3-flash", reasoning_effort="low")
    LLMFallbackConfig(provider="isoquant", model="glm-5.3-flash")
    with pytest.raises(ValueError, match="low, high, or max"):
        LLMConfig(provider="isoquant", model="glm-5.3-flash", reasoning_effort="none")
    with pytest.raises(ValueError, match=r"glm-5\.3-flash"):
        LLMConfig(provider="isoquant", model="other", reasoning_effort="low")


def test_factory_selects_isoquant_with_stage_credential():
    settings = SimpleNamespace(provider_stage_keys={"llm": "test-key"})
    service = build_llm_service(
        settings,
        {
            "provider": "isoquant",
            "model": "glm-5.3-flash",
            "reasoning_effort": "high",
            "max_tokens": 1024,
        },
        stage="llm",
    )
    assert isinstance(service, IsoquantLLMService)
    assert service._settings.model == "glm-5.3-flash"
    assert service._settings.max_tokens == 1024
    assert service.reasoning_effort == "high"


def test_isoquant_can_be_primary_with_first_token_fallback():
    settings = SimpleNamespace(
        provider_stage_keys={"llm": "isoquant-key", "llm_fallback": "groq-key"}
    )
    service = build_llm_service(
        settings,
        {
            "provider": "isoquant",
            "model": "glm-5.3-flash",
            "reasoning_effort": "low",
            "max_tokens": 1024,
            "fallback": {
                "provider": "groq",
                "model": "llama-3.1-8b-instant",
                "first_token_timeout_seconds": 3,
            },
        },
        stage="llm",
    )
    assert isinstance(service, IsoquantLLMService)
    assert service._fallback_service._settings.model == "llama-3.1-8b-instant"
    assert service.active_provider == "isoquant"


@pytest.mark.asyncio
async def test_isoquant_stream_sends_json_zdr_and_pipecat_context():
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert not request.url.query
        assert request.headers["Isoquant-ZDR"] == "required"
        assert request.headers["content-type"] == "application/json"
        assert payload["model"] == "glm-5.3-flash"
        assert payload["max_tokens"] == 1024
        assert payload["reasoning_effort"] == "low"
        assert payload["include_reasoning"] is False
        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}
        assert payload["messages"][-1] == {"role": "user", "content": "Hello!"}
        assert "temperature" not in payload
        assert "top_p" not in payload
        events = [
            {
                "id": "test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3-flash",
                "choices": [{"index": 0, "delta": {"content": "Hi!"}, "finish_reason": None}],
            },
            {
                "id": "test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3-flash",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
            {
                "id": "test",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "glm-5.3-flash",
                "choices": [],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        ]
        body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    service = IsoquantLLMService(
        api_key="test-key",
        settings=IsoquantLLMService.Settings(model="glm-5.3-flash", max_tokens=1024),
    )
    service._client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://api.isoquant.ai/v1",
        default_headers={"Isoquant-ZDR": "required"},
        http_client=transport_client,
    )
    try:
        stream = await service.get_chat_completions(
            LLMContext(messages=[{"role": "user", "content": "Hello!"}])
        )
        chunks = [chunk async for chunk in stream]
    finally:
        await service._client.close()
    assert len(seen) == 1
    assert chunks[0].choices[0].delta.content == "Hi!"
    assert chunks[-1].usage.total_tokens == 5


@pytest.mark.asyncio
async def test_isoquant_rejects_stream_without_completion_marker():
    def respond(_request: httpx.Request) -> httpx.Response:
        event = {
            "id": "test",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "glm-5.3-flash",
            "choices": [{"index": 0, "delta": {"content": "partial"}, "finish_reason": None}],
        }
        return httpx.Response(
            200,
            text=f"data: {json.dumps(event)}\n\n",
            headers={"content-type": "text/event-stream", "x-request-id": "req-test"},
        )

    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    service = IsoquantLLMService(
        api_key="test-key",
        settings=IsoquantLLMService.Settings(model="glm-5.3-flash", max_tokens=1024),
    )
    service._client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://api.isoquant.ai/v1",
        http_client=transport_client,
    )
    try:
        stream = await service.get_chat_completions(
            LLMContext(messages=[{"role": "user", "content": "Hello!"}])
        )
        with pytest.raises(RuntimeError, match=r"ended before completion.*req-test"):
            _ = [chunk async for chunk in stream]
    finally:
        await service._client.close()
