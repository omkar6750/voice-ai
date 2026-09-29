"""Recording API contracts; generated dashboard contracts derive from these models."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class RecordingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    kind: str
    created_at: datetime
    size_bytes: int | None
    sha256: str | None
    duration_seconds: float | None
    expires_at: datetime | None
    deleted_at: datetime | None
    deletion_requested_at: datetime | None
    storage_backend: Literal["local", "cloudinary", "supabase"]
    storage_status: str
    storage_error: str | None
    deletion_error: str | None


class RecordingListResponse(BaseModel):
    artifacts: list[RecordingResponse]
    total: int


class RecordingDeletionSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["artifacts", "runs", "calls", "utc_range", "all_current_org"]
    ids: list[str] = Field(default_factory=list, max_length=10000)
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_selection(self):
        if self.scope in {"artifacts", "runs", "calls"}:
            if not self.ids or self.start or self.end:
                raise ValueError("Select explicit database IDs only")
        elif self.scope == "utc_range":
            if self.ids or not self.start or not self.end or self.start >= self.end:
                raise ValueError("Provide an increasing UTC range")
            if self.start.utcoffset().total_seconds() or self.end.utcoffset().total_seconds():
                raise ValueError("Range boundaries must be UTC")
        elif self.ids or self.start or self.end:
            raise ValueError("All-current-org selection accepts no IDs or range")
        return self


class RecordingDeletionPreviewResponse(BaseModel):
    operation_id: str
    confirmation_token: str
    expires_at: datetime
    artifact_ids: list[str]
    size_bytes: int
    excluded: int
    confirmation_text: str


class RecordingDeletionExecute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_token: str = Field(min_length=20, max_length=200)
    confirmation_text: str


class RecordingDeletionItemResponse(BaseModel):
    artifact_id: str
    status: str
    error: str | None


class RecordingDeletionResponse(BaseModel):
    id: str
    status: str
    total: int
    deleted: int
    failed: int
    pending: int
    items: list[RecordingDeletionItemResponse]


class RecordingDeletionListResponse(BaseModel):
    operations: list[RecordingDeletionResponse]
