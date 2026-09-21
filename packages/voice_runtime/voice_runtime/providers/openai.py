from dataclasses import dataclass

from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.stt import OpenAISTTService
from pipecat.services.openai.tts import OpenAITTSService

from voice_runtime.config import AgentConfig


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str
    llm_model: str = "gpt-4.1-mini"
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "alloy"


def create_openai_services(settings: OpenAISettings, config: AgentConfig):
    stt = OpenAISTTService(api_key=settings.api_key, model=settings.stt_model)
    llm = OpenAILLMService(
        api_key=settings.api_key,
        settings=OpenAILLMService.Settings(
            model=settings.llm_model,
            system_instruction=config.system_prompt,
        ),
    )
    tts = OpenAITTSService(
        api_key=settings.api_key,
        settings=OpenAITTSService.Settings(model=settings.tts_model, voice=settings.tts_voice),
    )
    return stt, llm, tts
