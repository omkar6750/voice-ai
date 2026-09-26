from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateBrowserSessionRequest(BaseModel):
    agent_version_id: str | None = None
    contact_id: str | None = None
    phone_number: str | None = None
    contact_variables: dict[str, Any] | None = None
    logging_override: bool | None = None


class BrowserSessionResponse(BaseModel):
    id: str
    run_id: str
    status: str
    contact_id: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None


class WebRTCOfferRequest(BaseModel):
    sdp: str
    type: str = "offer"
    pc_id: str | None = None
    restart_pc: bool | None = None
    request_data: Any | None = None


class IceCandidatePatch(BaseModel):
    candidate: str
    sdp_mid: str = Field(default="0", alias="sdpMid")
    sdp_mline_index: int = Field(default=0, alias="sdpMLineIndex")

    model_config = {"populate_by_name": True}


class WebRTCPatchRequest(BaseModel):
    pc_id: str
    candidates: list[IceCandidatePatch]
