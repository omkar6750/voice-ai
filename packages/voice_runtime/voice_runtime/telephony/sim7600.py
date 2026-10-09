from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import replace

import serial

from voice_runtime.safe_logs import RuntimeEvent, operational_event
from voice_runtime.telephony.base import CallState, TelephonyTransport
from voice_runtime.telephony.outcome import determine_outcome
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
        self._events = deque(maxlen=64)
        self._release_snapshot = None
        self._monitor_task = None
        self._event_callback = None
        self._event_loop = None
        self._idle_pending = bytearray()
        self._local_hangup_ns = None
        self._event_count = 0

    async def open(self) -> None:
        if self._serial is None:
            self._serial = await asyncio.to_thread(
                self._serial_factory, self.port, self.baudrate, timeout=0.1, write_timeout=2
            )

    async def close(self) -> None:
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None
        if self._serial is not None:
            await asyncio.to_thread(self._serial.close)
            self._serial = None

    async def dial(self, phone_number: str) -> None:
        await self.open()
        self._disconnect_observed = False
        self._events.clear()
        self._event_count = 0
        self._release_snapshot = None
        self._local_hangup_ns = None
        await self._command(f"ATD{phone_number};")

    async def answer(self) -> None:
        await self.open()
        self._disconnect_observed = False
        self._events.clear()
        self._event_count = 0
        self._release_snapshot = None
        self._local_hangup_ns = None
        await self._command("ATA")

    async def hangup(self) -> None:
        await self.open()
        self._local_hangup_ns = time.time_ns()
        self._observe("local_hangup", "local")
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
        if self._disconnect_observed:
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
        if previous_state == CallState.ACTIVE and result in (
            CallState.IDLE,
            CallState.DISCONNECTED,
        ):
            self._observe("call_cleared", "poll")
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
            )
        )

    async def disconnect_status(self) -> ModemStatus:
        """Read the small, relevant disconnect snapshot under a fixed time budget."""
        await self.open()
        commands = ("AT+CEER", "AT", "AT+CREG?", "AT+CEREG?", "AT+CSQ", "AT+CPIN?", "AT+CLCC")
        results: dict[str, list[str]] = {}
        errors: list[str] = []
        try:
            async with asyncio.timeout(5):
                for command in commands:
                    try:
                        results[command] = await self._command(command, timeout_secs=0.8)
                    except Exception as exc:
                        errors.append(
                            command + ":timeout"
                            if isinstance(exc, (TimeoutError, ModemCommandTimeoutError))
                            else command + ":command_error"
                        )
        except TimeoutError:
            errors.append("snapshot_timeout")
        status = ModemStatusReader().from_results(
            results, serial_connected=self._serial is not None, errors=errors
        )
        report = next(
            (
                line.split(":", 1)[1].strip()
                for line in results.get("AT+CEER", [])
                if line.startswith("+CEER:")
            ),
            None,
        )
        self._captured_report = redact_at_response(report) if report is not None else None
        self._captured_errors = errors
        if self._disconnect_observed:
            return replace(status, call_state=CallState.DISCONNECTED)
        return status

    def _observe(self, signal: str, source: str, **details) -> None:
        event = {
            "signal": signal,
            "source": source,
            "observed_at_ns": time.time_ns(),
            "sequence": self._event_count + 1,
            **details,
        }
        self._events.append(event)
        self._event_count += 1
        if self._event_callback is not None and self._event_loop is not None:
            self._event_loop.call_soon_threadsafe(self._event_callback, event)

    def _handle_unsolicited(self, line: str, source: str, command: str | None = None) -> bool:
        if not line:
            return False
        expected = command.split("=", 1)[0].rstrip("?")[2:] if command else None
        prefix = line.split(":", 1)[0]
        unsolicited = (
            source == "urc"
            or (
                command not in {"ATI", "AT+CGMR"}
                and line not in {"OK", "ERROR", command}
                and not line.startswith(("+CME ERROR", "+CMS ERROR"))
                and prefix != expected
            )
            or line.startswith(("+CLCC:", "+CREG:", "+CEREG:"))
            or (
                line in {"NO CARRIER", "BUSY", "NO ANSWER", "NO DIALTONE"}
                or line.startswith("VOICE CALL END")
                or (
                    line.startswith("+")
                    and prefix != expected
                    and not line.startswith(("+CME ERROR", "+CMS ERROR"))
                )
            )
        )
        if unsolicited:
            if line.startswith(("+CLCC:", "+CREG:", "+CEREG:", "VOICE CALL END")) or line in {
                "NO CARRIER",
                "BUSY",
                "NO ANSWER",
                "NO DIALTONE",
            }:
                safe = re.sub(r'"[^"\r\n]*"', '"<redacted>"', redact_at_response(line))
            else:
                # Unknown URCs are retained by type, hash and size; their payload may be
                # an SMS body, a location or private subscriber information.
                import hashlib

                safe = (
                    prefix
                    if re.fullmatch(r"[+A-Z_ ]{1,64}", prefix)
                    else "unclassified_serial_line"
                ) + ":<redacted>"
                payload = line.split(":", 1)[1].strip() if ":" in line else ""
                if payload and re.fullmatch(r"[-+0-9, ]{1,240}", payload):
                    # Small numeric status/cause fields remain useful for new firmware
                    # URCs; long subscriber/device identifiers are still redacted.
                    safe = prefix + ":" + redact_at_response(payload)
                self._observe(
                    safe + ":sha256=" + hashlib.sha256(line.encode()).hexdigest(),
                    source,
                    payload_bytes=len(line.encode()),
                )
                safe = None
            if safe is not None:
                self._observe(safe, source)
        if line in {"NO CARRIER", "BUSY", "NO ANSWER", "NO DIALTONE"} or line.startswith(
            "VOICE CALL END"
        ):
            self._disconnect_observed = True
        elif line.startswith(("+CREG:", "+CEREG:")):
            # Preserve just registration status, excluding cell/location identifiers.
            fields = line.split(":", 1)[1].strip().split(",")
            status = fields[1] if len(fields) > 1 and fields[1].strip().isdigit() else fields[0]
            self._observe(line.split(":", 1)[0] + ":" + status.strip(), source)
        elif line.startswith("+CLCC:"):
            state = parse_call_state([line])
            if state == CallState.DISCONNECTED:
                self._disconnect_observed = True
                self._observe("call_cleared", source)
        return unsolicited

    def _read_idle_sync(self) -> None:
        try:
            raw = self._serial.readline()
            self._idle_pending.extend(raw)
            if len(self._idle_pending) > 8192:
                self._idle_pending.clear()
                self._observe("serial_response_overflow", "urc")
            while b"\n" in self._idle_pending:
                raw_line, _, rest = self._idle_pending.partition(b"\n")
                self._idle_pending[:] = rest
                self._handle_unsolicited(raw_line.decode("ascii", errors="replace").strip(), "urc")
        except OSError:
            self._observe("serial_io_error", "transport")
            raise

    def set_event_sink(self, callback) -> None:
        self._event_callback = callback
        self._event_loop = asyncio.get_running_loop()

    async def start_monitoring(self, callback) -> None:
        self.set_event_sink(callback)
        # Firmware may reject an optional notification setting; retain that coverage gap.
        for command in ("AT+CMEE=2", "AT+CLCC=1", "AT+CREG=1", "AT+CEREG=1"):
            try:
                await self._command(command, timeout_secs=0.8)
            except ModemCommandError:
                self._observe("notification_setup_failed:" + command, "setup")
        if self._monitor_task is None:
            self._monitor_task = asyncio.create_task(self._monitor())

    async def _monitor(self) -> None:
        while True:
            async with self._command_lock:
                read = asyncio.create_task(asyncio.to_thread(self._read_idle_sync))
                try:
                    await asyncio.shield(read)
                except asyncio.CancelledError:
                    await asyncio.gather(read, return_exceptions=True)
                    raise
                except OSError:
                    return
            await asyncio.sleep(0.02)

    async def capture_release(self) -> dict:
        # Freeze before cleanup's CHUP/ATH; never overwrite with cleanup side effects.
        if self._release_snapshot is None:
            status = await self.disconnect_status()
            self._release_snapshot = determine_outcome(
                events=list(self._events),
                report=self._captured_report,
                errors=list(self._captured_errors),
                registration={
                    "voice_registered": status.voice_registered
                    if status.voice_registration_known
                    else None,
                    "data_registered": status.data_registered
                    if status.data_registration_known
                    else None,
                    "sim_ready": status.sim_ready if status.sim_status_known else None,
                    "rssi": status.rssi,
                },
            ).snapshot()
        self._release_snapshot.setdefault("event_count", self._event_count)
        self._release_snapshot.setdefault(
            "summary_truncated", self._event_count > len(self._events)
        )
        return self._release_snapshot

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
        pending = self._idle_pending
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
                    was_unsolicited = self._handle_unsolicited(line, "command", command)
                    if line in {"NO CARRIER", "BUSY", "NO ANSWER", "NO DIALTONE"}:
                        self._disconnect_observed = True
                        response = {
                            "NO CARRIER": "no_carrier",
                            "BUSY": "busy",
                            "NO ANSWER": "no_answer",
                            "NO DIALTONE": "no_dialtone",
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
                        at_response_line=(
                            line.split(":", 1)[0] + ":<redacted>"
                            if was_unsolicited
                            else redact_at_response(line)
                        ),
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
            self._observe("serial_io_error", "transport")
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
