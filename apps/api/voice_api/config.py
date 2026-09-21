from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://voice:voice@localhost:55432/voice"
    openai_api_key: str | None = None
    openai_llm_model: str = "gpt-4.1-mini"
    openai_stt_model: str = "gpt-4o-mini-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"
    modem_at_port: str = ""
    modem_baudrate: int = 115200
    audio_input_device_index: int | None = None
    audio_output_device_index: int | None = None
    recordings_dir: str = "data/recordings"

    model_config = SettingsConfigDict(env_prefix="VOICE_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
