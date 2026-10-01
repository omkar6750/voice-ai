import httpx
import pytest
from voice_api.core.config import Settings
from voice_api.services import provider_registry


@pytest.mark.asyncio
async def test_live_models_cached_and_filtered(monkeypatch):
    provider_registry._cache.clear()
    calls = []

    def respond(request):
        calls.append(request.url.path)
        if "groq.com" in request.url.host:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "llama-3.1-8b-instant", "active": True},
                        {"id": "whisper-large-v3", "active": True},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-2.5-flash",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/gemini-embedding-001",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        provider_registry.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(respond)),
    )
    settings = Settings(_env_file=None, groq_api_key="fake", gemini_api_key="fake")
    first = await provider_registry.get_provider_registry(settings)
    second = await provider_registry.get_provider_registry(settings)
    assert len(calls) == 2
    assert first == second
    providers = {item.provider: item for item in first.providers}
    assert providers["groq"].models == ["llama-3.1-8b-instant"]
    assert providers["gemini"].models == ["gemini-2.5-flash"]
    assert providers["sarvam"].slots == ["llm", "stt", "tts"]
    assert providers["sarvam"].models_by_slot["llm"] == [
        "sarvam-105b",
        "sarvam-105b-conversations",
    ]
    assert providers["cartesia"].fields["pace"].runtime_supported is False


@pytest.mark.asyncio
async def test_unconfigured_models_are_not_invented():
    registry = await provider_registry.get_provider_registry(
        Settings(_env_file=None, groq_api_key=None, gemini_api_key=None)
    )
    providers = {item.provider: item for item in registry.providers}
    assert providers["groq"].models == []
    assert providers["gemini"].models == []
    assert providers["sarvam"].status == "configured"
