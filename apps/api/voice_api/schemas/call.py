from pydantic import BaseModel, Field


class TelephonySelection(BaseModel):
    provider: str = Field(default="sim7600", pattern=r"^(sim7600|twilio)$")
    connection_id: str | None = None
    from_number: str | None = None
    endpoint_id: str | None = None


class StartCallBody(BaseModel):
    contact_id: str
    agent_version_id: str
    endpoint_id: str | None = None
    telephony: TelephonySelection | None = None
    logging_override: bool | None = None
    dispatch: bool = False
