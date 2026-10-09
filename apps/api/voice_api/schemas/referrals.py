from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from voice_runtime.contracts.referrals import SaveReferralArguments


class ReferralResponse(SaveReferralArguments):
    id: str
    referrer_contact_id: str | None
    source_run_id: str | None
    promoted_contact_id: str | None
    status: Literal["pending_review", "reviewed", "dismissed", "converted"]
    phone_verification_status: Literal["unverified", "verified"]
    email_verification_status: Literal["unverified", "verified"]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferralPage(BaseModel):
    referrals: list[ReferralResponse]
    next_cursor: str | None = None


class ReferralReview(SaveReferralArguments):
    status: Literal["pending_review", "reviewed", "dismissed"] = "pending_review"
    phone_verification_status: Literal["unverified", "verified"] = "unverified"
    email_verification_status: Literal["unverified", "verified"] = "unverified"
    expected_updated_at: datetime


class ReferralPromotionResponse(BaseModel):
    status: Literal["converted"] = "converted"
    contact_id: str
    existing_contact: bool


class ReferralToolResponse(BaseModel):
    tool_id: str
    tool_version_id: str
    name: str = "save_referral"
