from typing import Protocol

from voice_runtime.telephony.base import TelephonyTransport


class Modem(TelephonyTransport, Protocol):
    async def answer(self) -> None: ...

    async def start_usb_audio(self) -> None: ...

    async def stop_usb_audio(self) -> None: ...
