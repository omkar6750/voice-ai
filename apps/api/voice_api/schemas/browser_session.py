from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateBrowserSessionRequest(BaseModel):
    agent_id: str | None = None
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
    sample_rate: int = 16000
