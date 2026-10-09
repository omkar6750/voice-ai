from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import replace

import serial

from voice_runtime.safe_logs import RuntimeEvent, operational_event
from voice_runtime.telephony.base import CallState, TelephonyTransport
from voice_runtime.telephony.status import ModemStatus, ModemStatusReader, parse_call_state


class ModemCommandError(RuntimeError):
    pass


class ModemCommandTimeoutError(ModemCommandError):
    pass


def redact_at_response(line: str) -> str:
    """Remove subscriber, device, and phone identifiers from AT logs."""
    redacted = re.sub(r"(?i)\b(IMEI|IMSI|ICCID)\s*:?\s*\d+", r"\1: <redacted>", line)
    redacted = re.sub(r"(?<!\d)\d{14,20}(?!\d)", "<redacted>", redacted)
    redacted = re.sub(r'"\+?\d{7,}"', '"<number>"', redacted)
    redacted = re.sub(r"(?<!\d)\+?\d{7,15}(?!\d)", "<number>", redacted)
    return redacted[:240]


class Sim7600Modem(TelephonyTransport):
    """SIM7600 AT command adapter. USB audio is enabled through AT commands."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        serial_factory: Callable[..., object] = serial.Serial,
        command_timeout: float = 5.0,
        trace=None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self._serial_factory = serial_factory
        self._serial: object | None = None
        self.command_timeout = command_timeout
        self._command_lock = asyncio.Lock()
        self.trace = trace
        self._disconnect_observed = False
        self._last_call_state: CallState | None = None

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
        self._disconnect_observed = False
        await self._command(f"ATD{phone_number};")

    async def answer(self) -> None:
        await self.open()
        self._disconnect_observed = False
        await self._command("ATA")

    async def hangup(self) -> None:
        await self.open()
        try:
            await self._command("AT+CHUP")
        except ModemCommandError:
            await self._command("ATH")

    async def state(self) -> CallState:
        await self.open()
        try:
            result = parse_call_state(await self._command("AT+CLCC"))
        except ModemCommandError:
            if not self._disconnect_observed:
                raise
            result = CallState.DISCONNECTED
        previous_state = self._last_call_state
        if self.trace is not None and result != previous_state:
            self.trace.record(
                "modem_state", component="modem", call_state=result.value, source="poll"
            )
            if previous_state == CallState.ACTIVE and result in (
                CallState.IDLE,
                CallState.DISCONNECTED,
            ):
                self.trace.record(
                    "call_disconnect_detected",
                    component="modem",
                    call_state=result.value,
                    source="poll",
                )
        self._last_call_state = result
        return result

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
            await self._command(f"AT+CPCMFRM={target}")
        operational_event(RuntimeEvent.PCM_CONFIGURED, sample_rate=sample_rate)

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

    async def disconnect_status(self) -> ModemStatus:
        """Read the small, relevant disconnect snapshot under a fixed time budget."""
        await self.open()
        commands = ("AT", "AT+CREG?", "AT+CSQ", "AT+CLCC", "AT+CPCMREG?")
        results: dict[str, list[str]] = {}
        errors: list[str] = []
        try:
            async with asyncio.timeout(5):
                for command in commands:
                    try:
                        results[command] = await self._command(command, timeout_secs=0.8)
                    except Exception as exc:
                        errors.append(
                            "timeout"
                            if isinstance(exc, (TimeoutError, ModemCommandTimeoutError))
                            else "command_error"
                        )
        except TimeoutError:
            errors.append("snapshot_timeout")
        status = ModemStatusReader().from_results(
            results, serial_connected=self._serial is not None, errors=errors
        )
        if self._disconnect_observed:
            return replace(status, call_state=CallState.DISCONNECTED)
        return status

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

    async def _command(self, command: str, *, timeout_secs: float | None = None) -> list[str]:
        if self._serial is None:
            raise ModemCommandError("modem is not open")
        async with self._command_lock:
            command_task = asyncio.create_task(
                asyncio.to_thread(self._command_sync, command, timeout_secs)
            )
            try:
                return await asyncio.shield(command_task)
            except asyncio.CancelledError:
                try:
                    await command_task
                except Exception:
                    pass
                raise

    def _command_sync(self, command: str, timeout: float | None = None) -> list[str]:
        serial_port = self._serial
        label = "ATD<number>;" if command.startswith("ATD") else command
        safe_command = label
        started = time.monotonic()
        if self.trace is not None:
            self.trace.record("command_started", component="modem", command=safe_command)
        operational_event(
            RuntimeEvent.MODEM_COMMAND,
            status="started",
            component="modem",
            at_command=safe_command,
        )
        lines: list[str] = []
        pending = bytearray()
        outcome = "unknown"
        response_bytes = 0
        try:
            serial_port.write((command + "\r").encode("ascii"))
            deadline = time.monotonic() + (timeout or self.command_timeout)
            while time.monotonic() < deadline:
                raw = serial_port.readline()
                if not raw:
                    continue
                response_bytes += len(raw)
                pending.extend(raw)
                if response_bytes > 8192:
                    outcome = "io"
                    raise ModemCommandError("AT response exceeded 8192 bytes")
                while b"\n" in pending:
                    raw_line, _, rest = pending.partition(b"\n")
                    pending[:] = rest
                    line = raw_line.decode("ascii", errors="replace").strip()
                    if not line or line == command:
                        continue
                    if line in {"NO CARRIER", "BUSY", "NO ANSWER"}:
                        self._disconnect_observed = True
                        response = {
                            "NO CARRIER": "no_carrier",
                            "BUSY": "busy",
                            "NO ANSWER": "no_answer",
                        }[line]
                        outcome = response
                        if self.trace is not None:
                            self.trace.record(
                                "call_disconnect_detected",
                                component="modem",
                                response=response,
                                source="urc",
                            )
                        operational_event(
                            RuntimeEvent.MODEM_RESPONSE,
                            response="rejected",
                            component="modem",
                            at_command=safe_command,
                            at_response_line=line,
                        )
                        raise ModemCommandError(f"modem rejected {label}: {line}")
                    response_class = (
                        "ok"
                        if line == "OK"
                        else "rejected"
                        if line == "ERROR" or line.startswith(("+CME ERROR", "+CMS ERROR"))
                        else "data"
                    )
                    operational_event(
                        RuntimeEvent.MODEM_RESPONSE,
                        response=response_class,
                        component="modem",
                        at_command=safe_command,
                        at_response_line=redact_at_response(line),
                    )
                    lines.append(line)
                    if line == "OK":
                        outcome = "ok"
                        return lines
                    if line == "ERROR" or line.startswith(("+CME ERROR", "+CMS ERROR")):
                        outcome = "rejected"
                        raise ModemCommandError(f"modem rejected {label}: {line}")
            outcome = "timeout"
            raise ModemCommandTimeoutError(f"timed out waiting for response to {label}")
        except OSError:
            outcome = "io"
            raise
        finally:
            if self.trace is not None:
                self.trace.record(
                    "command_finished",
                    component="modem",
                    command=safe_command,
                    response=outcome,
                    duration_ms=(time.monotonic() - started) * 1000,
                )
