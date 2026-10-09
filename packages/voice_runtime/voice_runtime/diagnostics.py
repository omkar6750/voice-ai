import argparse
import asyncio
import json
import math
from collections.abc import Mapping
from typing import Any

from serial.tools import list_ports
from voice_shared.dev_visibility import is_development, redact_api_keys

from voice_runtime.contracts.diagnostics import diagnostic_dict
from voice_runtime.safe_logs import error_category
from voice_runtime.telephony.sim7600 import Sim7600Modem

_PROVIDERS = frozenset(
    {"groq", "gemini", "cartesia", "sarvam", "jev", "whatsapp", "openrouter", "isoquant", "gnani"}
)
_SOURCES = frozenset({"provider", "modem", "transport", "call", "evidence", "runtime"})
_FAILURES = {
    "runtime_exception": ("runtime_failure", "Runtime execution failed"),
    "call_execution_failed": ("runtime_failure", "Call execution failed"),
    "tool_error": ("tool_failure", "Tool execution failed"),
    "jev_request_failed": ("provider_request_failed", "Provider request failed"),
    "whatsapp_request_failed": ("provider_request_failed", "Provider request failed"),
    "whatsapp_tool_unconfigured": ("tool_configuration", "WhatsApp tool is not configured"),
    "whatsapp_template_unconfigured": ("tool_configuration", "WhatsApp template is not configured"),
    "whatsapp_template_invalid": (
        "tool_configuration",
        "WhatsApp template configuration is invalid",
    ),
    **{
        f"{provider}_classifier_failed": ("provider_request_failed", "Classifier request failed")
        for provider in _PROVIDERS
    },
}


def _provider(value) -> str:
    return value if type(value) is str and value in _PROVIDERS else "provider"


def _source(value) -> str:
    return value if type(value) is str and value in _SOURCES else "runtime"


def _status(value) -> int | None:
    return value if type(value) is int and 100 <= value <= 599 else None


def _response(exc):
    try:
        return getattr(exc, "response", None)
    except Exception:
        return None


def _response_status(response):
    try:
        return _status(getattr(response, "status_code", None))
    except Exception:
        return None


def provider_error_diagnostic(
    *,
    provider: str,
    status_code: int | None = None,
    body: Mapping[str, Any] | str | None = None,
    request_id: str | None = None,
    retry_after_seconds: float | None = None,
) -> dict:
    """Normalize provider response failures without retaining raw response bodies."""
    provider = _provider(provider)
    status_code = _status(status_code)
    body_map = body if type(body) is dict else {}
    error = body_map.get("error") if body_map else None
    error_map = error if type(error) is dict else {}
    provider_message = (
        error_map.get("message")
        or body_map.get("message")
        or body_map.get("error_description")
        or (body if type(body) is str else None)
    )
    # Development retains the complete body; classification uses a bounded view.
    lower = provider_message[:2000].lower() if type(provider_message) is str else ""
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
    elif status_code == 402 or (
        status_code == 429
        and any(
            term in lower
            for term in ("quota", "credits", "credit exhausted", "usage limit", "billing")
        )
    ):
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
    elif status_code == 400:
        if error_map.get("code") == "tool_use_failed":
            code, message = (
                "provider_tool_call_invalid",
                f"{provider} could not generate a valid tool call",
            )
        elif "no user query found" in lower:
            code, message = (
                "provider_context_invalid",
                f"{provider} requires a user query in the conversation context",
            )
        else:
            code, message = (
                "provider_invalid_request",
                f"{provider} rejected the request configuration or context",
            )
        category, retryable = "provider_request_failed", False
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
        code=code,
        message=message,
        detail=redact_api_keys(provider_message)[:2000]
        if is_development() and type(provider_message) is str
        else None,
        retryable=retryable,
        provider_request_id=redact_api_keys(request_id)[:255]
        if is_development() and isinstance(request_id, str)
        else None,
        http_status=status_code,
        retry_after_seconds=_retry_after(retry_after_seconds),
        metadata={
            "provider": provider,
            **(
                {"provider_error": redact_api_keys(body)}
                if is_development() and body is not None
                else {}
            ),
        },
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
    response = _response(exc)
    status_code = _response_status(response)
    if status_code is not None and source == "provider":
        try:
            body = response.json()
        except Exception:
            body = None
        return provider_error_diagnostic(
            provider="provider",
            status_code=status_code,
            body=body,
        )
    code = code if type(code) is str and code in _FAILURES else "runtime_exception"
    category, message = _FAILURES[code]
    return diagnostic_dict(
        severity="error",
        category=category,
        source=_source(source),  # type: ignore[arg-type]
        code=code,
        message=message,
        detail=redact_api_keys(str(exc))[:2000] if is_development() else None,
        retryable=retryable is True,
        uncertain=uncertain is True,
        metadata={
            "error_category": error_category(exc),
            **({"raw_error": redact_api_keys(str(exc))} if is_development() else {}),
        },
    )


def provider_exception_diagnostic(exc: BaseException, *, provider: str, operation: str) -> dict:
    """Extract safe provider response metadata from SDK exceptions across providers."""
    # The Gnani SDK wraps WebSocket handshake errors; inspect a bounded
    # cause chain for HTTP metadata without retaining vendor error text.
    cause = exc
    response = None
    status_code = None
    for _ in range(5):
        response = _response(cause)
        status_code = _response_status(response) or _status(getattr(cause, "status_code", None))
        if status_code is not None:
            break
        next_cause = getattr(cause, "__cause__", None)
        if next_cause is None or next_cause is cause:
            break
        cause = next_cause
    body = None
    if response is not None:
        try:
            body = response.json()
        except Exception:
            body = getattr(response, "text", None) if is_development() else None
    if is_development() and body is None:
        body = getattr(cause, "body", None)
        if not isinstance(body, (dict, str)):
            body = {"message": str(cause)}
    try:
        retry_after = (getattr(response, "headers", {}) or {}).get("retry-after")
    except Exception:
        retry_after = None
    diagnostic = provider_error_diagnostic(
        provider=provider,
        status_code=status_code,
        body=body,
        retry_after_seconds=_retry_after(retry_after),
    )
    if status_code in {None, 200} and isinstance(cause, (TimeoutError, ConnectionError, OSError)):
        diagnostic.update(
            category="provider_unavailable",
            code="provider_transport_failed",
            message=f"{_provider(provider)} connection failed",
            retryable=True,
        )
    # Development retains provider request IDs for support and correlation.
    if is_development() or provider in {"gnani", "isoquant"}:
        headers = getattr(response, "headers", {}) or {}
        request_id = headers.get("x-request-id") or headers.get("request-id")
        if (
            type(request_id) is str
            and len(request_id) <= 255
            and all(char.isascii() and (char.isalnum() or char in "_-:.") for char in request_id)
        ):
            diagnostic["provider_request_id"] = request_id
    if type(operation) is str and operation in {"llm", "stt", "tts", "classifier", "embedding"}:
        diagnostic["metadata"]["operation"] = operation
    diagnostic["metadata"]["error_category"] = error_category(exc)
    return diagnostic


def _retry_after(value: Any) -> float | None:
    if type(value) not in (str, int, float):
        return None
    try:
        number = float(value)
        return max(0.0, min(number, 86400.0)) if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def text_error_diagnostic(error: object, *, fallback_source: str = "runtime") -> dict:
    """Classify provider-shaped pipeline text when an SDK hides HTTP fields."""
    detail = redact_api_keys(error)[:2000] if is_development() and type(error) is str else None
    lower = error[:2000].lower() if type(error) is str else ""
    fallback_source = _source(fallback_source)
    provider = next(
        (
            name
            for name in (
                "groq",
                "gemini",
                "cartesia",
                "sarvam",
                "jev",
                "whatsapp",
                "openrouter",
                "isoquant",
                "gnani",
            )
            if name in lower
        ),
        None,
    )
    metadata = {"provider": provider} if provider else {}
    if is_development():
        metadata["raw_error"] = redact_api_keys(error)
    if any(term in lower for term in ("tpm", "rate limit", "rate_limit", "throttl")):
        return diagnostic_dict(
            severity="error",
            category="provider_rate_limit",
            source="provider" if provider else fallback_source,  # type: ignore[arg-type]
            code="provider_throttled",
            message=f"{provider or 'Provider'} throttled the request",
            detail=detail,
            retryable=True,
            metadata=metadata,
        )
    if any(
        term in lower for term in ("quota", "credits", "credit exhausted", "usage limit", "billing")
    ):
        return diagnostic_dict(
            severity="error",
            category="provider_quota_exhausted",
            source="provider" if provider else fallback_source,  # type: ignore[arg-type]
            code="provider_quota_exhausted",
            message=f"{provider or 'Provider'} usage limit or quota was reached",
            detail=detail,
            retryable=False,
            metadata=metadata,
        )
    if any(term in lower for term in ("api key", "unauthorized", "invalid key", "authentication")):
        return diagnostic_dict(
            severity="error",
            category="provider_authentication",
            source="provider" if provider else fallback_source,  # type: ignore[arg-type]
            code="provider_authentication_failed",
            message=f"{provider or 'Provider'} rejected the configured credentials",
            detail=detail,
            retryable=False,
            metadata=metadata,
        )
    return diagnostic_dict(
        severity="error",
        category="pipeline_failure",
        source=fallback_source,  # type: ignore[arg-type]
        code="pipeline_error",
        message="Pipecat pipeline failed",
        detail=detail,
        metadata=metadata,
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
