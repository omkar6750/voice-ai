"""Strict response contracts for human callback scheduling."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class CallbackSlotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    display: str


class CallbackAvailabilityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "no_availability"]
    requested_timeframe: str
    slots: list[CallbackSlotResponse]
    message: str | None


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
