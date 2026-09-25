"""Normalize an explicit international destination; never guess a country or timezone."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from voice_runtime.contracts.base import ConfigModel


class ContactBody(ConfigModel):
    name: str = Field(min_length=1, max_length=120)
    phone_number: str
    timezone: str | None = None
    business: str | None = None
    source: str | None = None
    language: str | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        number = re.sub(r"[\s().-]", "", value)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", number):
            raise ValueError("Use an international phone number including +country code")
        return number

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError("Use a valid IANA timezone or leave unknown") from None
        return value


class ContactPatchBody(ConfigModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone_number: str | None = None
    timezone: str | None = None
    business: str | None = None
    source: str | None = None
    language: str | None = None
    metadata_json: dict | None = None

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        number = re.sub(r"[\s().-]", "", value)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", number):
            raise ValueError("Use an international phone number including +country code")
        return number

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ValueError, ZoneInfoNotFoundError):
                raise ValueError("Use a valid IANA timezone or leave unknown") from None
        return value
