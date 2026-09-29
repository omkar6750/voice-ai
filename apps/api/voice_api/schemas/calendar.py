"""Strict response contracts for human callback scheduling."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CallbackSlotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    display: str


class CallbackAvailabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "no_availability", "partial_availability"]
    requested_timeframe: str
    slots: list[CallbackSlotResponse]
    message: str | None
    warnings: list[str] = Field(default_factory=list)


class CallbackAvailabilityErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "timezone_required",
        "contact_unavailable",
        "invalid_timeframe",
        "configuration_error",
        "calendar_unavailable",
        "availability_check_failed",
    ]
    requested_timeframe: str
    message: str


CallbackAvailabilityResult = Annotated[
    CallbackAvailabilityResponse | CallbackAvailabilityErrorResponse,
    Field(discriminator="status"),
]


class CallbackBookingConfirmedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["confirmed"]
    callback_id: str
    scheduled_time: str
    duration_minutes: int = Field(gt=0)


class CallbackSlotConflictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["slot_conflict"]
    message: str


CallbackBookingResponse = Annotated[
    CallbackBookingConfirmedResponse | CallbackSlotConflictResponse,
    Field(discriminator="status"),
]
