from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from voice_runtime.telephony.status import ModemStatus


class CallState(StrEnum):
    IDLE = "idle"
    DIALING = "dialing"
    RINGING = "ringing"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"


class TelephonyTransport(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def dial(self, phone_number: str) -> None: ...

    async def hangup(self) -> None: ...

    async def state(self) -> CallState: ...

    async def status(self) -> ModemStatus: ...
