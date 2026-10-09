"""Normalize an explicit international destination; never guess a country or timezone."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator
from voice_runtime.contracts.base import ConfigModel


class ContactBody(ConfigModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone_number: str
    timezone: str | None = None
    business: str | None = None
    source: str | None = None
    language: str | None = None
    metadata_json: dict | None = None

    @model_validator(mode="after")
    def require_name(self):
        if not self.name or not self.first_name:
            raise ValueError("Provide a first name and optionally a last name")
        return self

    @model_validator(mode="before")
    @classmethod
    def normalize_name_parts(cls, values):
        if not isinstance(values, dict):
            return values
        values = dict(values)
        name = values.get("name")
        first = values.get("first_name")
        last = values.get("last_name")
        if first is not None:
            first = first.strip()
            last = last.strip() if last is not None else ""
            values["first_name"] = first
            values["last_name"] = last or None
            values["name"] = " ".join(part for part in (first, last) if part)
        elif name:
            parts = name.split()
            values["name"] = " ".join(parts)
            values["first_name"] = parts[0] if parts else None
            values["last_name"] = " ".join(parts[1:]) or None
        return values

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
    first_name: str | None = Field(default=None, min_length=1, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    phone_number: str | None = None
    timezone: str | None = None
    business: str | None = None
    source: str | None = None
    language: str | None = None
    metadata_json: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_name(cls, values):
        if not isinstance(values, dict):
            return values
        values = dict(values)
        if values.get("name") is not None and "first_name" not in values:
            parts = values["name"].split()
            values["name"] = " ".join(parts)
            values["first_name"] = parts[0] if parts else None
            values["last_name"] = " ".join(parts[1:]) or None
        elif values.get("first_name") is not None:
            values["first_name"] = values["first_name"].strip()
            last = values.get("last_name")
            values["last_name"] = last.strip() if last and last.strip() else None
        return values

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


class VariableDescriptor(ConfigModel):
    key: str = Field(..., description="Template variable token (e.g. business or campaign)")
    label: str = Field(..., description="Human-readable label for UI badge")
    source: str = Field(..., description="Origin of the variable: column, metadata, or temporal")
    description: str | None = Field(default=None, description="Help text or sample values")


class ContactVariablesResponse(ConfigModel):
    columns: list[VariableDescriptor] = Field(default_factory=list)
    metadata_keys: list[VariableDescriptor] = Field(default_factory=list)
    temporal: list[VariableDescriptor] = Field(default_factory=list)
