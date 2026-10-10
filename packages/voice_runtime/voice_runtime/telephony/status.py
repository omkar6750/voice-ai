import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from voice_runtime.telephony.base import CallState


@dataclass(frozen=True)
class ModemStatus:
    alive: bool = False
    serial_connected: bool = False
    sim_ready: bool = False
    voice_registered: bool = False
    data_registered: bool = False
    packet_attached: bool = False
    can_make_call: bool = False
    active_call: bool = False
    call_state: CallState = CallState.DISCONNECTED
    rssi: int | None = None
    signal_quality: int | None = None
    operator: str | None = None
    radio_access: str = "unknown"
    band: str | None = None
    roaming: bool = False
    usb_audio_supported: bool = False
    usb_audio_active: bool = False
    available_transports: tuple[str, ...] = field(default_factory=tuple)
    voice_registration_known: bool = False
    data_registration_known: bool = False
    sim_status_known: bool = False
    last_error: str | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def endpoint_payload(self) -> dict:
        from voice_shared.contracts import ModemEndpointStatus

        values = asdict(self)
        values.pop("available_transports")
        values["call_state"] = self.call_state.value
        return ModemEndpointStatus.model_validate(values).model_dump(mode="json")


@dataclass(frozen=True)
class ParsedRegistration:
    registered: bool
    roaming: bool


def parse_csq(lines: list[str]) -> tuple[int | None, int | None]:
    match = next((re.search(r"\+CSQ:\s*(\d+),\s*(\d+)", line) for line in lines), None)
    if not match:
        return None, None
    rssi, quality = (int(value) for value in match.groups())
    return (None if rssi == 99 else rssi), (None if quality == 99 else quality)


def parse_registration(lines: list[str], prefix: str) -> ParsedRegistration:
    match = next((re.search(rf"\{prefix}:\s*\d+,(\d+)", line) for line in lines), None)
    if not match:
        return ParsedRegistration(False, False)
    status = int(match.group(1))
    return ParsedRegistration(status in {1, 5}, status == 5)


def parse_bool(lines: list[str], prefix: str) -> bool:
    return any(re.search(rf"\{prefix}:\s*1", line) for line in lines)


def parse_operator(lines: list[str]) -> str | None:
    match = next((re.search(r'\+COPS:\s*\d+,\s*\d+,"([^"]*)"', line) for line in lines), None)
    return match.group(1) or None if match else None


def parse_cpsi(lines: list[str]) -> tuple[str, str | None]:
    line = next((line for line in lines if line.startswith("+CPSI:")), "")
    if not line:
        return "unknown", None
    fields = [field.strip() for field in line.split(":", 1)[1].split(",")]
    radio = fields[0].upper() if fields else "unknown"
    if radio not in {"LTE", "WCDMA", "GSM"}:
        radio = "unknown"
    band = next((field for field in fields if "BAND" in field.upper()), None)
    return radio, band


def parse_call_state(lines: list[str]) -> CallState:
    line = next((line for line in lines if line.startswith("+CLCC:")), None)
    if line is None:
        return CallState.IDLE
    fields = [field.strip() for field in line.split(":", 1)[1].split(",")]
    if len(fields) < 3:
        return CallState.IDLE
    return {
        "0": CallState.ACTIVE,
        "1": CallState.ACTIVE,
        "2": CallState.DIALING,
        "3": CallState.DIALING,
        "4": CallState.RINGING,
        "5": CallState.RINGING,
        "6": CallState.DISCONNECTED,
    }.get(fields[2], CallState.IDLE)


class ModemStatusReader:
    """Builds a provider-neutral status snapshot from SIM7600 AT responses."""

    def from_results(
        self,
        results: dict[str, list[str]],
        *,
        serial_connected: bool,
        errors: list[str] | None = None,
    ) -> ModemStatus:
        alive = "AT" in results
        sim_ready = any("+CPIN: READY" in line for line in results.get("AT+CPIN?", []))
        voice = parse_registration(results.get("AT+CREG?", []), "+CREG")
        data = parse_registration(results.get("AT+CEREG?", []), "+CEREG")
        rssi, quality = parse_csq(results.get("AT+CSQ", []))
        radio, band = parse_cpsi(results.get("AT+CPSI?", []))
        active_state = parse_call_state(results.get("AT+CLCC", []))
        usb_supported = "AT+CPCMREG?" in results
        usb_active = parse_bool(results.get("AT+CPCMREG?", []), "+CPCMREG")
        packet_attached = parse_bool(results.get("AT+CGATT?", []), "+CGATT")
        available: list[str] = []
        if voice.registered:
            available.append("cellular_voice")
        if data.registered and packet_attached:
            available.append("lte_data" if radio == "LTE" else "packet_data")
        if usb_supported:
            available.append("usb_audio")
        can_make_call = (
            alive
            and sim_ready
            and voice.registered
            and active_state in {CallState.IDLE, CallState.DISCONNECTED}
            and rssi is not None
            and rssi > 0
        )
        return ModemStatus(
            alive=alive,
            serial_connected=serial_connected,
            sim_ready=sim_ready,
            voice_registered=voice.registered,
            voice_registration_known=any(
                line.startswith("+CREG:") for line in results.get("AT+CREG?", [])
            ),
            data_registration_known=any(
                line.startswith("+CEREG:") for line in results.get("AT+CEREG?", [])
            ),
            sim_status_known=any(line.startswith("+CPIN:") for line in results.get("AT+CPIN?", [])),
            data_registered=data.registered,
            packet_attached=packet_attached,
            can_make_call=can_make_call,
            active_call=active_state
            in {
                CallState.DIALING,
                CallState.RINGING,
                CallState.ACTIVE,
            },
            call_state=active_state,
            rssi=rssi,
            signal_quality=quality,
            operator=parse_operator(results.get("AT+COPS?", [])),
            radio_access=radio,
            band=band,
            roaming=voice.roaming or data.roaming,
            usb_audio_supported=usb_supported,
            usb_audio_active=usb_active,
            available_transports=tuple(available),
            last_error="; ".join(errors or []) or None,
        )
