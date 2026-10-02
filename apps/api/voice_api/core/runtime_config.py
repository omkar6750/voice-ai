"""Server-only settings for the separate runtime boundary."""

from functools import lru_cache

from pydantic import Field

from voice_api.core.config import Settings


class RuntimeControlSettings(Settings):
    runtime_separate_enabled: bool = True
    runtime_control_token: str | None = Field(default=None, repr=False)
    runtime_control_token_previous: str | None = Field(default=None, repr=False)
    runtime_service_token_previous: str | None = Field(default=None, repr=False)
    runtime_base_url: str = "http://127.0.0.1:8001"
    runtime_public_base_url: str = "http://127.0.0.1:8001"
    max_concurrent_calls: int = Field(default=4, ge=1, le=32)


@lru_cache
def get_runtime_settings():
    return RuntimeControlSettings()


def use_separate_runtime() -> bool:
    settings = get_runtime_settings()
    # This activation is intentionally local; hosted call routing is unchanged.
    return (
        settings.env.casefold() in {"dev", "development", "local"}
        and settings.runtime_separate_enabled
    )
