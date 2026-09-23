"""Environment credentials/settings still consumed by the protected demo script."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class DemoProviderSettings(BaseSettings):
    cartesia_api_key: str = ""
    sarvam_api_key: str
    groq_api_key: str
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_template_name: str = "dialtone_followup"
    whatsapp_header_media_id: str = ""
    jev_api_key: str = ""

    model_config = SettingsConfigDict(env_prefix="VOICE_", env_file=".env", extra="ignore")
