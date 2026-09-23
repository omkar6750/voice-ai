from pydantic import BaseModel, Field


class RevisionBody(BaseModel):
    revision: int = Field(gt=0)
    config: dict
    note: str | None = None


class ExpectedRevision(BaseModel):
    revision: int = Field(gt=0)


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: dict


class BindToolBody(BaseModel):
    revision: int = Field(gt=0)
    binding_key: str = Field(min_length=1, max_length=80, pattern="^[a-z][a-z0-9_]*$")
    tool_version_id: str
    config: dict = Field(default_factory=dict)


class ActivateAgentBody(BaseModel):
    version_id: str
