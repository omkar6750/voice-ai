from dataclasses import dataclass

from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pydantic_settings import BaseSettings, SettingsConfigDict

from voice_runtime.config import AgentConfig


class DemoProviderSettings(BaseSettings):
    cartesia_api_key: str = ""
    cartesia_voice_id: str = "71a7ad14-091c-4e8e-a314-022ece01c121"
    sarvam_api_key: str
    sarvam_stt_model: str = "saaras:v3"
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_voice: str = "ritu"
    sarvam_tts_language: str = "en-IN"
    tts_provider: str = "sarvam"
    groq_api_key: str
    groq_llm_model: str = "qwen/qwen3.8-27b"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = "dialtone_followup"
    whatsapp_header_media_id: str = ""
    jev_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="VOICE_", env_file=".env", extra="ignore")


@dataclass(frozen=True)
class DemoServices:
    stt: SarvamSTTService
    llm: GroqLLMService
    tts: CartesiaTTSService | SarvamTTSService


def create_demo_services(settings: DemoProviderSettings, config: AgentConfig) -> DemoServices:
    stt = SarvamSTTService(
        api_key=settings.sarvam_api_key,
        settings=SarvamSTTService.Settings(model=settings.sarvam_stt_model),
        sample_rate=16000,
    )
    llm = GroqLLMService(
        api_key=settings.groq_api_key,
        settings=GroqLLMService.Settings(
            model=settings.groq_llm_model,
            system_instruction=config.system_prompt,
            reasoning_effort="none",
            temperature=0.2,
            max_tokens=256,
        ),
    )
    if settings.tts_provider.lower() == "sarvam":
        tts: CartesiaTTSService | SarvamTTSService = SarvamTTSService(
            api_key=settings.sarvam_api_key,
            settings=SarvamTTSService.Settings(
                model=settings.sarvam_tts_model,
                voice=settings.sarvam_tts_voice,
                language=settings.sarvam_tts_language,
            ),
            sample_rate=16000,
        )
    else:
        tts = CartesiaTTSService(
            api_key=settings.cartesia_api_key,
            settings=CartesiaTTSService.Settings(voice=settings.cartesia_voice_id),
            sample_rate=16000,
            encoding="pcm_s16le",
            container="raw",
        )
    return DemoServices(stt=stt, llm=llm, tts=tts)
