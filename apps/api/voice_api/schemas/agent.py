from pydantic import BaseModel, Field, field_validator
from voice_runtime.contracts import AgentConfig
from voice_runtime.contracts.evidence import PromptResolutionRecord


class RevisionBody(BaseModel):
    revision: int = Field(gt=0)
    config: AgentConfig
    note: str | None = None


class ExpectedRevision(BaseModel):
    revision: int = Field(gt=0)


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: AgentConfig


class AgentVersionResponse(BaseModel):
    id: str
    version: int
    revision: int
    status: str
    config: AgentConfig
    note: str | None

    @field_validator("config", mode="before")
    @classmethod
    def readable_legacy_configuration(cls, value):
        # Existing immutable versions must remain readable so operators can clone/fix them.
        return AgentConfig.model_validate(value, context={"read_legacy_config": True})


class AgentVersionsResponse(BaseModel):
    versions: list[AgentVersionResponse]


class UpdatedAgentVersionResponse(BaseModel):
    id: str
    revision: int
    config: AgentConfig


class BindToolBody(BaseModel):
    revision: int = Field(gt=0)
    binding_key: str = Field(min_length=1, max_length=80, pattern="^[a-z][a-z0-9_]*$")
    tool_version_id: str
    config: dict = Field(default_factory=dict)


class ActivateAgentBody(BaseModel):
    version_id: str


class AgentVersionSummaryResponse(BaseModel):
    id: str
    version: int
    revision: int
    status: str
    note: str | None


class AgentVersionSummariesResponse(BaseModel):
    versions: list[AgentVersionSummaryResponse]


class PromptPreviewBody(BaseModel):
    config: AgentConfig
    node_id: str
    contact_values: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    fact_values: dict[str, str | int | float | bool] = Field(default_factory=dict)


class PromptPreviewResponse(BaseModel):
    node_id: str
    rendered: dict
    resolution: list[PromptResolutionRecord]
    refresh: str
