from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILES = (str(_REPO_ROOT / ".env"), ".env")


class Settings(BaseSettings):
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://voice:voice@localhost:55432/voice"
    cartesia_api_key: str | None = None
    sarvam_api_key: str | None = None
    groq_api_key: str | None = None
    recordings_dir: str = "data/recordings"
    integration_keys: str | None = None
    integration_active_key: str | None = None
    operator_token: str | None = None
    gemini_api_key: str | None = None
    integration_media_dir: str = "data/integration-media"

    model_config = SettingsConfigDict(
        env_prefix="VOICE_",
        env_file=_ENV_FILES,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
