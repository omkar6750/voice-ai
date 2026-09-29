from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILES = (
    str(_REPO_ROOT / ".env.main-copy"),
    str(_REPO_ROOT / ".env"),
    str(_REPO_ROOT / ".env.local"),
    ".env",
    ".env.local",
)


class Settings(BaseSettings):
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://voice:voice@localhost:55432/voice"
    cartesia_api_key: str | None = None
    sarvam_api_key: str | None = None
    groq_api_key: str | None = None
    jev_api_key: str | None = None
    recordings_dir: str = "data/recordings"
    integration_keys: str | None = None
    integration_active_key: str | None = None
    callback_slot_signing_key: str | None = None
    runtime_service_token: str | None = None
    clerk_secret_key: str | None = Field(default=None, validation_alias="CLERK_SECRET_KEY")
    clerk_publishable_key: str | None = Field(
        default=None, validation_alias="CLERK_PUBLISHABLE_KEY"
    )
    clerk_authorized_parties: str = "http://localhost:5173,http://localhost:8000"
    clerk_webhook_signing_secret: str | None = Field(
        default=None, validation_alias="CLERK_WEBHOOK_SIGNING_SECRET"
    )
    organization_creation_enabled: bool = True
    public_base_url: str | None = None
    gemini_api_key: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    google_calendar_client_id: str | None = None
    google_calendar_client_secret: str | None = None
    google_calendar_redirect_uri: str = (
        "http://localhost:8000/api/v1/calendar-integrations/google/callback"
    )

    model_config = SettingsConfigDict(
        env_prefix="VOICE_",
        env_file=_ENV_FILES,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
