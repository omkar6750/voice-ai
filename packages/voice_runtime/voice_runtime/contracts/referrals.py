"""Fixed arguments for capturing a caller-provided referral in one operation."""

from pydantic import Field, field_validator

from .base import ConfigModel


class SaveReferralArguments(ConfigModel):
    first_name: str = Field(
        min_length=1,
        max_length=120,
        description="Referred person's first name as given; do not use the caller's name.",
    )
    last_name: str | None = Field(
        default=None, max_length=120, description="Surname only if supplied; otherwise omit."
    )
    phone_number: str | None = Field(
        default=None,
        max_length=80,
        description="Caller-supplied referral phone as confirmed in readback. Do not invent a country code; omit if unknown.",
    )
    email: str | None = Field(
        default=None,
        max_length=254,
        description="Caller-supplied referral email confirmed in readback, or omit.",
    )
    organization: str | None = Field(
        default=None,
        max_length=240,
        description="Organization explicitly established in this conversation, or omit.",
    )
    role: str | None = Field(
        default=None, max_length=240, description="Referred person's stated role, or omit."
    )
    context: str | None = Field(
        default=None,
        max_length=2000,
        description="Brief factual referral reason and relevant context from the caller; no guesses.",
    )
    contact_details_confirmed: bool = Field(
        default=False,
        description="True only after the caller confirms the phone/email read back once. This confirms transcription, not ownership or permission to contact.",
    )

    @field_validator(
        "first_name",
        "last_name",
        "phone_number",
        "email",
        "organization",
        "role",
        "context",
        mode="before",
    )
    @classmethod
    def trim_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


REFERRAL_DESCRIPTION = (
    "Save a pending referral when the caller directs us to another person. Ask once for their "
    "name and best way to reach them, accepting phone, email, both, or an incomplete referral. "
    "Use organization/role/context already stated; leave unknown fields empty. Do not guess "
    "a surname, country code, email, or company. If phone/email is supplied, read the supplied "
    "details back once and wait for confirmation before saving with contact_details_confirmed=true. "
    "One call saves all fields. Say it was saved only after status=saved. This records unverified "
    "details for review and never calls, messages, or creates a dialable contact."
)


def referral_parameters() -> dict:
    return SaveReferralArguments.model_json_schema()
