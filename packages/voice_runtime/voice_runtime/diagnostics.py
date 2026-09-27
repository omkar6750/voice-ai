import argparse
import asyncio
import json
import re
from collections.abc import Mapping
from typing import Any

from serial.tools import list_ports

from voice_runtime.contracts.diagnostics import diagnostic_dict
from voice_runtime.telephony.sim7600 import Sim7600Modem


def _safe_text(value: Any, limit: int = 2000) -> str | None:
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\b(?:sk|gsk|key|token)[-_][A-Za-z0-9._-]+\b", "[REDACTED]", text)
    text = re.sub(r"(?i)(api[_ -]?key|access[_ -]?token|password|secret)\s*[:=]\s*[^,;\s]+", r"\1=[REDACTED]", text)
    return text[:limit]


def provider_error_diagnostic(
    *,
    provider: str,
    status_code: int | None = None,
    body: Mapping[str, Any] | str | None = None,
    request_id: str | None = None,
    retry_after_seconds: float | None = None,
) -> dict:
    """Normalize provider response failures without retaining raw response bodies."""
    body_map = body if isinstance(body, Mapping) else {}
    error = body_map.get("error") if body_map else None
    error_map = error if isinstance(error, Mapping) else {}
    provider_code = error_map.get("code") or body_map.get("code")
    provider_message = (
        error_map.get("message")
        or body_map.get("message")
        or body_map.get("error_description")
        or (body if isinstance(body, str) else None)
    )
    lower = str(provider_message or "").lower()
    if status_code in {401, 403} or (
        status_code is None
        and any(term in lower for term in ("api key", "unauthorized", "forbidden"))
    ):
        category, code, message, retryable = (
            "provider_authentication",
            "provider_authentication_failed",
            f"{provider} rejected the configured credentials",
            False,
        )
    elif status_code == 429 and any(term in lower for term in ("quota", "credit", "usage limit", "billing")):
        category, code, message, retryable = (
            "provider_quota_exhausted",
            "provider_quota_exhausted",
            f"{provider} usage limit or quota was reached",
            False,
        )
    elif status_code == 429:
        category, code, message, retryable = (
            "provider_rate_limit",
            "provider_throttled",
            f"{provider} throttled the request",
            True,
        )
    elif status_code is not None and status_code >= 500:
        category, code, message, retryable = (
            "provider_unavailable",
            "provider_server_error",
            f"{provider} is temporarily unavailable",
            True,
        )
    else:
        category, code, message, retryable = (
            "provider_request_failed",
            "provider_request_failed",
            f"{provider} request failed",
            False,
        )
    return diagnostic_dict(
        severity="error",
        category=category,
        source="provider",
        code=str(provider_code or code),
        message=message,
        detail=_safe_text(provider_message),
        retryable=retryable,
        provider_request_id=_safe_text(request_id, 255),
        http_status=status_code,
        retry_after_seconds=retry_after_seconds,
        metadata={"provider": provider},
    )


def exception_diagnostic(
    exc: BaseException,
    *,
    source: str = "runtime",
    category: str = "runtime_failure",
    code: str = "runtime_exception",
    message: str = "Runtime execution failed",
    retryable: bool = False,
    uncertain: bool = False,
) -> dict:
    """Normalize an exception for final progress fallback."""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code is not None and source == "provider":
        try:
            body = response.json()
        except Exception:
            body = None
        return provider_error_diagnostic(
            provider="provider",
            status_code=status_code,
            body=body,
            request_id=(getattr(response, "headers", {}) or {}).get("x-request-id"),
        )
    return diagnostic_dict(
        severity="error",
        category=category,
        source=source,  # type: ignore[arg-type]
        code=code,
        message=message,
        detail=_safe_text(exc),
        retryable=retryable,
        uncertain=uncertain,
    )


def text_error_diagnostic(error: str, *, fallback_source: str = "runtime") -> dict:
    """Classify provider-shaped pipeline text when an SDK hides HTTP fields."""
    text = _safe_text(error) or "Runtime execution failed"
    lower = text.lower()
    provider = next(
        (name for name in ("groq", "cartesia", "sarvam", "jev", "whatsapp") if name in lower),
        None,
    )
    if any(term in lower for term in ("tpm", "rate limit", "rate_limit", "throttl")):
        return diagnostic_dict(
            severity="error",
            category="provider_rate_limit",
            source="provider" if provider else fallback_source,  # type: ignore[arg-type]
            code="provider_throttled",
            message=f"{provider or 'Provider'} throttled the request",
            detail=text,
            retryable=True,
            metadata={"provider": provider} if provider else {},
        )
    if any(term in lower for term in ("quota", "credits", "credit exhausted", "usage limit", "billing")):
        return diagnostic_dict(
            severity="error",
            category="provider_quota_exhausted",
            source="provider" if provider else fallback_source,  # type: ignore[arg-type]
            code="provider_quota_exhausted",
            message=f"{provider or 'Provider'} usage limit or quota was reached",
            detail=text,
            retryable=False,
            metadata={"provider": provider} if provider else {},
        )
    if any(term in lower for term in ("api key", "unauthorized", "invalid key", "authentication")):
        return diagnostic_dict(
            severity="error",
            category="provider_authentication",
            source="provider" if provider else fallback_source,  # type: ignore[arg-type]
            code="provider_authentication_failed",
            message=f"{provider or 'Provider'} rejected the configured credentials",
            detail=text,
            retryable=False,
            metadata={"provider": provider} if provider else {},
        )
    return diagnostic_dict(
        severity="error",
        category="pipeline_failure",
        source=fallback_source,  # type: ignore[arg-type]
        code="pipeline_error",
        message="Pipecat pipeline failed",
        detail=text,
    )


def modem_status_metadata(status) -> dict[str, Any]:
    return {
        "alive": status.alive,
        "serial_connected": status.serial_connected,
        "sim_ready": status.sim_ready,
        "voice_registered": status.voice_registered,
        "data_registered": status.data_registered,
        "packet_attached": status.packet_attached,
        "call_state": status.call_state.value,
        "rssi": status.rssi,
        "signal_quality": status.signal_quality,
        "operator": status.operator,
        "radio_access": status.radio_access,
        "band": status.band,
        "usb_audio_active": status.usb_audio_active,
    }


def list_serial_ports() -> list[dict[str, str | None]]:
    return [
        {"device": port.device, "description": port.description, "hwid": port.hwid}
        for port in list_ports.comports()
    ]


async def read_status(port: str, baudrate: int) -> dict[str, object]:
    modem = Sim7600Modem(port, baudrate)
    try:
        return {
            "modem": (await modem.status()).__dict__,
            "serial_ports": list_serial_ports(),
        }
    finally:
        await modem.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect SIM7600 modem and serial status")
    parser.add_argument("--modem-port", default="COM16")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()
    print(
        json.dumps(asyncio.run(read_status(args.modem_port, args.baudrate)), default=str, indent=2)
    )
