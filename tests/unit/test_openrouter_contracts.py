from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from voice_api.schemas.providers import OpenRouterModelQuery
from voice_api.services.openrouter_catalog import model_catalog
from voice_api.services.openrouter_client import ChatCompletion, OpenRouterClient


class MockTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models/user"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "qwen/qwen3.8-27b:free",
                            "name": "Qwen 3.8",
                            "architecture": {
                                "modality": "text->text",
                                "input_modalities": ["text"],
                                "output_modalities": ["text"],
                            },
                            "context_length": 32768,
                            "pricing": {
                                "prompt": "0",
                                "completion": "0",
                                "request": "0",
                                "image": "0",
                            },
                            "supported_parameters": ["tools", "response_format", "reasoning"],
                        },
                        {
                            "id": "openai/gpt-4.1",
                            "name": "GPT 4.1",
                            "architecture": {"modality": "text->text"},
                            "context_length": 100000,
                            "pricing": {"prompt": "0.000002", "completion": "0.000008"},
                            "supported_parameters": [],
                        },
                    ],
                    "total_count": 2,
                    "links": {"next": None},
                },
            )
        raise AssertionError(request.url)


@pytest.mark.asyncio
async def test_typed_client_parses_pricing_and_free_model():
    client = OpenRouterClient("secret")
    transport = MockTransport()
    original = httpx.AsyncClient

    class Client:
        def __init__(self, *args, **kwargs):
            self.client = original(transport=transport)

        async def __aenter__(self):
            return self.client

        async def __aexit__(self, *args):
            await self.client.aclose()

    import voice_api.services.openrouter_client as module

    monkey = pytest.MonkeyPatch()
    monkey.setattr(module.httpx, "AsyncClient", Client)
    try:
        page = await client.models(user=True, limit=1000, output_modalities="text")
    finally:
        monkey.undo()
    assert page.data[0].is_free
    assert page.data[1].pricing.prompt == Decimal("0.000002")
    assert page.data[0].supported_parameters == ["tools", "response_format", "reasoning"]


@pytest.mark.asyncio
async def test_catalog_filters_account_models_without_exposing_vendor_shape():
    class FakeClient:
        async def models(self, **kwargs):
            return type(
                "Page",
                (),
                {
                    "data": [
                        type(
                            "Model",
                            (),
                            {
                                "id": "qwen/qwen3.8-27b:free",
                                "name": "Qwen 3.8",
                                "architecture": type(
                                    "A",
                                    (),
                                    {
                                        "output_modalities": ["text"],
                                        "input_modalities": ["text"],
                                        "modality": "text->text",
                                    },
                                )(),
                                "context_length": 32768,
                                "max_completion_tokens": None,
                                "supported_parameters": ["tools"],
                                "pricing": type(
                                    "P",
                                    (),
                                    {
                                        "prompt": Decimal("0"),
                                        "completion": Decimal("0"),
                                        "request": Decimal("0"),
                                        "image": Decimal("0"),
                                    },
                                )(),
                                "is_free": True,
                            },
                        )()
                    ]
                },
            )()

    result = await model_catalog(
        FakeClient(), OpenRouterModelQuery(q="qwen", free_only=True, limit=1000)
    )
    assert result.total_count == 1
    assert result.items[0].id == "qwen/qwen3.8-27b:free"
    assert result.items[0].tool_calling is True
    assert result.next_offset is None


def test_chat_usage_preserves_openrouter_cost_and_byok_metadata():
    completion = ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "model": "qwen/qwen3.8-27b:free",
            "choices": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 15,
                "total_tokens": 25,
                "cost": 0.0012,
                "cost_details": {"upstream_inference_cost": 0.0004},
                "is_byok": True,
                "prompt_tokens_details": {"cached_tokens": 2},
                "completion_tokens_details": {"reasoning_tokens": 5},
            },
        }
    )
    assert completion.usage is not None
    assert completion.usage.total_cost == 0.0012
    assert completion.usage.cost_details["upstream_inference_cost"] == 0.0004
    assert completion.usage.is_byok is True


@pytest.mark.parametrize("stage", ["llm", "classifier", "summarizer"])
def test_runtime_factory_builds_openrouter_service_for_llm_stages(monkeypatch, stage):
    from pipecat.services.openrouter.llm import OpenRouterLLMService
    from voice_runtime.execution import llm_factory

    calls = []

    def stage_key(_settings, actual_stage, provider):
        calls.append((actual_stage, provider))
        return "org-scoped-run-lease"

    monkeypatch.setattr(llm_factory, "stage_api_key", stage_key)
    service = llm_factory.build_llm_service(
        SimpleNamespace(),
        {
            "provider": "openrouter",
            "model": "openai/gpt-4.1",
            "temperature": 0.2,
            "max_tokens": 64,
            "models": ["openai/gpt-4.1"],
            "provider_preferences": {
                "order": ["provider-a"],
                "allow_fallbacks": False,
            },
        },
        stage=stage,
    )

    assert isinstance(service, OpenRouterLLMService)
    assert service._settings.model == "openai/gpt-4.1"
    assert service._settings.extra == {
        "models": ["openai/gpt-4.1"],
        "provider": {"order": ["provider-a"], "allow_fallbacks": False},
    }
    assert calls == [(stage, "openrouter")]
