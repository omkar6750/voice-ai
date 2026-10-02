"""Write-only secrets and safe named credential metadata."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

CredentialProvider = Literal[
    "groq", "gemini", "openrouter", "sarvam", "isoquant", "cartesia", "jev", "twilio", "whatsapp"
]


class CredentialCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120, pattern=r"\S")
    provider: CredentialProvider
    api_key: SecretStr | None = None
    account_sid: str | None = Field(default=None, pattern=r"^AC[0-9a-fA-F]{32}$")
    api_key_sid: str | None = Field(default=None, pattern=r"^SK[0-9a-fA-F]{32}$")
    api_key_secret: SecretStr | None = None
    auth_token: SecretStr | None = None

    @model_validator(mode="after")
    def validate_secret(self):
        fields = (self.api_key, self.api_key_secret, self.auth_token)
        if any(
            value is not None and not 1 <= len(value.get_secret_value().strip()) <= 4096
            for value in fields
        ):
            raise ValueError("Credential secrets must contain 1-4096 characters")
        if self.provider == "twilio":
            if (
                not all((self.account_sid, self.api_key_sid, self.api_key_secret, self.auth_token))
                or self.api_key
            ):
                raise ValueError(
                    "Twilio requires Account SID, REST API key SID/secret and separate webhook auth token"
                )
        elif self.api_key is None or any(
            (self.account_sid, self.api_key_sid, self.api_key_secret, self.auth_token)
        ):
            raise ValueError("Provider requires only an API key or access token")
        return self

    def plaintext(self) -> str:
        import json

        if self.provider != "twilio":
            return self.api_key.get_secret_value().strip()
        return json.dumps(
            {
                "account_sid": self.account_sid,
                "api_key_sid": self.api_key_sid,
                "api_key_secret": self.api_key_secret.get_secret_value().strip(),
                "auth_token": self.auth_token.get_secret_value().strip(),
            },
            separators=(",", ":"),
        )


class CredentialReplace(CredentialCreate):
    expected_version: int = Field(gt=0)


class CredentialStatus(BaseModel):
    id: str
    name: str
    provider: CredentialProvider
    purpose: str
    version: int
    status: Literal["stored", "deleted", "unavailable"]
    configured: bool
    source: Literal["organization"] = "organization"
    updated_at: datetime | None
    deleted_at: datetime | None


class CredentialDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0)


class CredentialRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120, pattern=r"\S")
    expected_version: int = Field(gt=0)
