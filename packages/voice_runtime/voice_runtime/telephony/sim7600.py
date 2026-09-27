from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable

import serial
from loguru import logger

from voice_runtime.telephony.base import CallState, TelephonyTransport
from voice_runtime.telephony.status import ModemStatus, ModemStatusReader, parse_call_state


class ModemCommandError(RuntimeError):
    pass


def redact_at_response(line: str) -> str:
    """Remove subscriber, device, and phone identifiers from AT logs."""
    redacted = re.sub(r"(?i)\b(IMEI|IMSI|ICCID)\s*:?\s*\d+", r"\1: <redacted>", line)
    redacted = re.sub(r'"\+?\d{7,}"', '"<number>"', redacted)
    return re.sub(r"(?<!\d)\d{14,20}(?!\d)", "<redacted>", redacted)


class Sim7600Modem(TelephonyTransport):
    """SIM7600 AT command adapter. USB audio is enabled through AT commands."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        serial_factory: Callable[..., object] = serial.Serial,
        command_timeout: float = 5.0,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self._serial_factory = serial_factory
        self._serial: object | None = None
        self.command_timeout = command_timeout
        self._command_lock = asyncio.Lock()

    async def open(self) -> None:
        if self._serial is None:
            self._serial = await asyncio.to_thread(
                self._serial_factory, self.port, self.baudrate, timeout=0.1, write_timeout=2
            )

    async def close(self) -> None:
        if self._serial is not None:
            await asyncio.to_thread(self._serial.close)
            self._serial = None

    async def dial(self, phone_number: str) -> None:
        await self.open()
        await self._command(f"ATD{phone_number};")

    async def answer(self) -> None:
        await self.open()
        await self._command("ATA")

    async def hangup(self) -> None:
        await self.open()
        try:
            await self._command("AT+CHUP")
        except ModemCommandError:
            await self._command("ATH")

    async def state(self) -> CallState:
        await self.open()
        return parse_call_state(await self._command("AT+CLCC"))

    async def start_usb_audio(self) -> None:
        await self.open()
        await self._command("AT+CPCMREG=1")

    async def stop_usb_audio(self) -> None:
        await self.open()
        await self._command("AT+CPCMREG=0")

    async def get_pcm_format(self) -> int:
        """Query current PCM format (0 = 8kHz, 1 = 16kHz)."""
        await self.open()
        lines = await self._command("AT+CPCMFRM?")
        for line in lines:
            if line.startswith("+CPCMFRM:"):
                val = line.split(":", 1)[1].strip()
                try:
                    return int(val)
                except ValueError:
                    pass
        return 0

    async def ensure_pcm_format(self, sample_rate: int = 16000) -> None:
        """Ensure the modem PCM format matches requested rate (8000 or 16000)."""
        if sample_rate not in {8000, 16000}:
            raise ValueError("SIM7600 PCM sample rate must be 8000 or 16000 Hz")
        await self.open()
        target = 1 if sample_rate == 16000 else 0
        current = await self.get_pcm_format()
        if current != target:
            logger.info(
                "Modem PCM format is {} ({}); switching to {} ({}Hz)",
                current,
                "16kHz" if current == 1 else "8kHz",
                target,
                sample_rate,
            )
            await self._command(f"AT+CPCMFRM={target}")
        else:
            logger.info("Modem PCM format verified: {} ({}Hz)", target, sample_rate)

    async def status(self) -> ModemStatus:
        await self.open()
        return await self._read_status(
            (
                "AT",
                "AT+CPIN?",
                "AT+CSQ",
                "AT+CEREG?",
                "AT+CREG?",
                "AT+CGATT?",
                "AT+COPS?",
                "AT+CPSI?",
                "AT+CGACT?",
                "AT+CLCC",
                "AT+CPCMREG?",
                "ATI",
                "AT+CGMR",
                "AT+CEER",
            )
        )

    async def probe_status(self) -> ModemStatus:
        """Read the connection and SIM fields needed for a live endpoint card."""
        await self.open()
        return await self._read_status(
            (
                "AT",
                "AT+CPIN?",
                "AT+CSQ",
                "AT+CEREG?",
                "AT+CREG?",
                "AT+CGATT?",
                "AT+COPS?",
                "AT+CPSI?",
                "AT+CLCC",
                "AT+CPCMREG?",
            )
        )

    async def _read_status(self, commands: tuple[str, ...]) -> ModemStatus:
        results: dict[str, list[str]] = {}
        errors: list[str] = []
        for command in commands:
            try:
                results[command] = await self._command(command)
            except ModemCommandError as exc:
                errors.append(str(exc))
        return ModemStatusReader().from_results(
            results, serial_connected=self._serial is not None, errors=errors
        )

    async def _command(self, command: str) -> list[str]:
        if self._serial is None:
            raise ModemCommandError("modem is not open")
        async with self._command_lock:
            return await asyncio.to_thread(self._command_sync, command)

    def _command_sync(self, command: str) -> list[str]:
        serial_port = self._serial
        label = "ATD<number>;" if command.startswith("ATD") else command
        logger.info("AT TX {}", label)
        serial_port.write((command + "\r").encode("ascii"))
        lines: list[str] = []
        pending = bytearray()
        deadline = time.monotonic() + self.command_timeout
        while time.monotonic() < deadline:
            raw = serial_port.readline()
            if not raw:
                continue
            pending.extend(raw)
            if len(pending) > 8192:
                raise ModemCommandError("AT response exceeded 8192 bytes")
            while b"\n" in pending:
                raw_line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                line = raw_line.decode("ascii", errors="replace").strip()
                if not line or line == command:
                    continue
                logger.info("AT RX {}", redact_at_response(line.split(',"')[0]))
                lines.append(line)
                if line == "OK":
                    return lines
                if line in {"ERROR", "NO CARRIER", "BUSY", "NO ANSWER"} or line.startswith(
                    ("+CME ERROR", "+CMS ERROR")
                ):
                    raise ModemCommandError(f"modem rejected {label}: {line}")
        raise ModemCommandError(f"timed out waiting for response to {label}")
