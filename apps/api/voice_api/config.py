from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://voice:voice@localhost:55432/voice"
    cartesia_api_key: str | None = None
    cartesia_voice_id: str = "71a7ad14-091c-4e8e-a314-022ece01c121"
    sarvam_api_key: str | None = None
    sarvam_stt_model: str = "saaras:v3"
    groq_api_key: str | None = None
    groq_llm_model: str = "qwen/qwen3.8-27b"
    modem_at_port: str = "COM16"
    modem_audio_port: str = "COM17"
    modem_baudrate: int = 115200
    recordings_dir: str = "data/recordings"

    model_config = SettingsConfigDict(env_prefix="VOICE_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
