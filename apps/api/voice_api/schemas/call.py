from pydantic import BaseModel


class StartCallBody(BaseModel):
    contact_id: str
    agent_version_id: str
    endpoint_id: str | None = None
    logging_override: bool | None = None
    dispatch: bool = False

