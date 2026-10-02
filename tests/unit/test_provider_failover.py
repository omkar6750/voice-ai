"""Failover never replays content or function calls already emitted."""

from types import SimpleNamespace

import pytest
from voice_runtime.execution.isoquant import IsoquantStreamError
from voice_runtime.execution.llm_factory import _FirstTokenFallback


class Stream:
    def __init__(self, items):
        self.items = items
        self.closed = False

    async def events(self):
        for item in self.items:
            if isinstance(item, Exception):
                raise item
            yield item

    def __aiter__(self):
        return self.events()

    async def close(self):
        self.closed = True


def chunk(**values):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(**values))])


def service_for(items):
    primary = Stream(items)
    fallback = Stream([chunk(content="fallback reply")])

    class Primary:
        async def get_chat_completions(self, context):
            return primary

    class Fallback:
        async def get_chat_completions(self, context):
            return fallback

    class Service(_FirstTokenFallback, Primary):
        pass

    service = Service()
    service._primary_provider, service._primary_model = "isoquant", "glm-5.3-flash"
    service.configure_fallback(
        Fallback(),
        {
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "first_token_timeout_seconds": 1,
        },
    )
    return service, primary, fallback


@pytest.mark.asyncio
async def test_isoquant_truncation_before_output_activates_one_fallback():
    service, primary, fallback = service_for([IsoquantStreamError("incomplete stream")])
    stream = await service.get_chat_completions({})
    result = [item async for item in stream]
    assert result[0].choices[0].delta.content == "fallback reply"
    assert primary.closed
    assert service.active_provider == "groq"
    assert stream is fallback


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first", [chunk(content="partial answer"), chunk(tool_calls=[{"id": "call-1"}])]
)
async def test_failure_after_text_or_tool_fragment_never_activates_fallback(first):
    service, primary, fallback = service_for([first, IsoquantStreamError("incomplete stream")])
    stream = await service.get_chat_completions({})
    assert await anext(stream) is first
    with pytest.raises(IsoquantStreamError):
        await anext(stream)
    assert primary.closed
    assert not fallback.closed
    assert service.active_provider == "isoquant"
    assert not service._fallback_active
