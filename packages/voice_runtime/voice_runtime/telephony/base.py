from enum import StrEnum
from typing import Protocol


class CallState(StrEnum):
    IDLE = "idle"
    DIALING = "dialing"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"


class TelephonyTransport(Protocol):
    async def dial(self, phone_number: str) -> None: ...

    async def hangup(self) -> None: ...

    async def state(self) -> CallState: ...
