from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILES = (
    str(_API_ROOT / ".env"),
    str(_API_ROOT / ".env.local"),
)

MAX_CALL_DURATION_SECONDS = 600


class Settings(BaseSettings):
    env: str = "dev"
    debug_diagnostics: bool = False
    debug_perf: bool = False
    database_url: str = "postgresql+asyncpg://voice:voice@localhost:55432/voice"
    cartesia_api_key: str | None = None
    sarvam_api_key: str | None = None
    groq_api_key: str | None = None
    isoquant_api_key: str | None = None
    jev_api_key: str | None = None
    recordings_dir: str = "data/recordings"
    integration_keys: str | None = None
    integration_active_key: str | None = None
    callback_slot_signing_key: str | None = None
    runtime_service_token: str | None = None
    hosted_calls_enabled: bool = False
    max_concurrent_calls: int = Field(default=1, ge=1, le=1)
    call_max_duration_seconds: int = Field(
        default=MAX_CALL_DURATION_SECONDS, ge=1, le=MAX_CALL_DURATION_SECONDS
    )
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None
    recording_max_bytes: int = Field(default=100_000_000, ge=1, le=100_000_000)
    recording_quota_bytes: int | None = Field(default=None, ge=1)
    # None preserves explicit developer-configured providers for local reference
    # flows. Hosted organization/run resolution sets a dict (including {}) so
    # missing tenant credentials never fall back to process environment keys.
    provider_stage_keys: dict[str, str] | None = Field(default=None, repr=False)
    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None
    supabase_private_bucket: str = "voice-private"
    clerk_secret_key: str | None = Field(default=None, validation_alias="CLERK_SECRET_KEY")
    clerk_authorized_parties: str = "http://localhost:5173,http://localhost:8000"
    clerk_webhook_signing_secret: str | None = Field(
        default=None, validation_alias="CLERK_WEBHOOK_SIGNING_SECRET"
    )
    organization_creation_enabled: bool = True
    public_base_url: str | None = None
    gemini_api_key: str | None = None
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
