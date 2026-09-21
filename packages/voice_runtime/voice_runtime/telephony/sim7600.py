import asyncio
from collections.abc import Callable

import serial

from voice_runtime.telephony.base import CallState, TelephonyTransport


class ModemCommandError(RuntimeError):
    pass


class Sim7600Transport(TelephonyTransport):
    """Small AT-command adapter. Audio is handled by Pipecat local audio."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        serial_factory: Callable[..., object] = serial.Serial,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self._serial_factory = serial_factory
        self._serial: object | None = None

    async def open(self) -> None:
        if self._serial is None:
            self._serial = await asyncio.to_thread(
                self._serial_factory, self.port, self.baudrate, timeout=1
            )

    async def close(self) -> None:
        if self._serial is not None:
            await asyncio.to_thread(self._serial.close)
            self._serial = None

    async def dial(self, phone_number: str) -> None:
        await self.open()
        await self._command(f"ATD{phone_number};")

    async def hangup(self) -> None:
        await self.open()
        await self._command("ATH")

    async def state(self) -> CallState:
        await self.open()
        lines = await self._command("AT+CLCC")
        return CallState.ACTIVE if any(",0,0," in line for line in lines) else CallState.IDLE

    async def _command(self, command: str) -> list[str]:
        if self._serial is None:
            raise ModemCommandError("modem is not open")
        return await asyncio.to_thread(self._command_sync, command)

    def _command_sync(self, command: str) -> list[str]:
        serial_port = self._serial
        serial_port.write((command + "\r").encode("ascii"))
        lines: list[str] = []
        while True:
            raw = serial_port.readline()
            if not raw:
                raise ModemCommandError(f"timed out waiting for response to {command}")
            line = raw.decode("ascii", errors="replace").strip()
            if not line or line == command:
                continue
            lines.append(line)
            if line == "OK":
                return lines
            if line == "ERROR":
                raise ModemCommandError(f"modem rejected {command}")
