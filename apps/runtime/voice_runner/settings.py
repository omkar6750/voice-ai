from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    runtime_min_free_spool_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    env: str = "dev"
    api_base_url: str = "http://127.0.0.1:8000"
    runtime_public_base_url: str = "http://127.0.0.1:8001"
    runtime_control_token: SecretStr = Field(default=SecretStr(""), repr=False)
    runtime_control_token_previous: SecretStr = Field(default=SecretStr(""), repr=False)
    runtime_service_token: SecretStr = Field(default=SecretStr(""), repr=False)
    runtime_service_token_previous: SecretStr = Field(default=SecretStr(""), repr=False)
    runtime_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    recordings_dir: str = "data/runtime-recordings"
    runtime_spool_dir: str = "data/runtime-evidence"
    max_concurrent_calls: int = Field(default=4, ge=1, le=32)
    call_max_duration_seconds: int = Field(default=600, ge=1, le=600)
    runtime_cpu_budget: float = Field(default=1, gt=0)
    runtime_shutdown_seconds: int = Field(default=285, ge=1, le=285)
    runtime_max_loop_lag_ms: float = Field(default=100, gt=0)
    debug_perf: bool = False
    hosted_calls_enabled: bool = False
    model_config = SettingsConfigDict(
        env_prefix="VOICE_",
        env_file=(
            str(Path(__file__).resolve().parents[1] / ".env"),
            str(Path(__file__).resolve().parents[1] / ".env.local"),
        ),
        extra="ignore",
    )

    @property
    def local(self):
        return self.env.casefold() in {"dev", "development", "local"}

    def validate_deployment(self):
        if (
            not self.runtime_control_token.get_secret_value()
            or not self.runtime_service_token.get_secret_value()
        ):
            raise ValueError("Runtime control and service tokens are required")
        if not self.local and (
            not self.api_base_url.startswith("https://")
            or not self.runtime_public_base_url.startswith("https://")
        ):
            raise ValueError("Hosted runtime requires HTTPS service URLs")
        Path(self.runtime_spool_dir).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings():
    return RuntimeSettings()
