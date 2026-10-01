from types import SimpleNamespace

import pytest
from pipecat.services.sarvam.llm import SarvamLLMService
from voice_runtime.contracts.providers import LLMConfig, LLMFallbackConfig, MainLLMConfig
from voice_runtime.execution import llm_factory


def test_sarvam_models_are_valid_for_primary_and_fallback():
    LLMConfig(provider="sarvam", model="sarvam-105b")
    MainLLMConfig(
        provider="groq",
        model="llama-3.1-8b-instant",
        fallback=LLMFallbackConfig(provider="sarvam", model="sarvam-105b-conversations"),
    )
    MainLLMConfig(
        provider="groq",
        model="llama-3.1-8b-instant",
        fallback=LLMFallbackConfig(provider="groq", model="llama-3.1-8b-instant"),
    )
    LLMConfig(provider="sarvam", model="sarvam-105b", reasoning_effort="none")
    with pytest.raises(ValueError, match="This provider uses"):
        LLMConfig(provider="groq", reasoning_effort="low")


def test_sarvam_can_be_primary_with_provider_fallback(monkeypatch):
    keys = []
    monkeypatch.setattr(
        llm_factory,
        "stage_api_key",
        lambda _settings, stage, provider: keys.append((stage, provider)) or "org-key",
    )

    service = llm_factory.build_llm_service(
        SimpleNamespace(),
        {
            "provider": "sarvam",
            "model": "sarvam-105b",
            "reasoning_effort": "none",
            "fallback": {
                "provider": "groq",
                "model": "llama-3.1-8b-instant",
                "first_token_timeout_seconds": 3,
            },
        },
        stage="llm",
    )

    assert isinstance(service, SarvamLLMService)
    assert service._settings.model == "sarvam-105b"
    assert service._settings.reasoning_effort is None
    assert service._fallback_service._settings.model == "llama-3.1-8b-instant"
    assert keys == [("llm", "sarvam"), ("llm_fallback", "groq")]


def test_sarvam_can_be_selected_as_fallback(monkeypatch):
    keys = []
    monkeypatch.setattr(
        llm_factory,
        "stage_api_key",
        lambda _settings, stage, provider: keys.append((stage, provider)) or "org-key",
    )

    service = llm_factory.build_llm_service(
        SimpleNamespace(),
        {
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
            "fallback": {
                "provider": "sarvam",
                "model": "sarvam-105b-conversations",
                "first_token_timeout_seconds": 3,
            },
        },
        stage="llm",
    )

    assert service._settings.model == "llama-3.1-8b-instant"
    assert isinstance(service._fallback_service, SarvamLLMService)
    assert service._fallback_service._settings.model == "sarvam-105b-conversations"
    assert keys == [("llm", "groq"), ("llm_fallback", "sarvam")]


@pytest.mark.asyncio
async def test_fallback_provider_error_cycles_once_to_primary(monkeypatch):
    class PrimaryService:
        async def get_chat_completions(self, _context):
            return "primary-response"

    class FallbackService:
        async def get_chat_completions(self, _context):
            raise llm_factory._Non200ProviderStatusError(429)

    class CyclicService(llm_factory._FirstTokenFallback, PrimaryService):
        pass

    service = CyclicService()
    service._primary_provider = "primary"
    service._primary_model = "primary-model"
    service.configure_fallback(
        FallbackService(), {"provider": "fallback", "model": "fallback-model"}
    )
    service._activate_fallback(llm_factory._Non200ProviderStatusError(429))

    assert await service.get_chat_completions({}) == "primary-response"
    assert service._fallback_active is False
    assert service.active_provider == "primary"
    assert service.active_model == "primary-model"
