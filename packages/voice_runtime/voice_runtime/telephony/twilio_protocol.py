"""Validation helpers for Twilio voice callbacks and Media Stream handshakes."""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from twilio.request_validator import RequestValidator

_ACCOUNT_SID = re.compile(r"AC[0-9a-fA-F]{32}\Z")
_CALL_SID = re.compile(r"CA[0-9a-fA-F]{32}\Z")
_STREAM_SID = re.compile(r"MZ[0-9a-fA-F]{32}\Z")


def _valid_canonical_url(url: str, *, websocket: bool) -> bool:
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlsplit(url)
        # Accessing .port also rejects malformed ports and bracketed hosts.
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == ("wss" if websocket else "https")
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
        and "?" not in url
        and "#" not in url
        and "@" not in parsed.netloc
    )


def validate_twilio_signature(
    auth_token: str,
    canonical_url: str,
    params: Mapping[str, Any],
    signature: str | None,
    *,
    websocket: bool = False,
) -> bool:
    """Validate Twilio's signature for a trusted, canonical public URL.

    The URL must come from application configuration, never forwarded headers.
    Twilio documents one compatibility fallback for WSS handshakes: a trailing
    slash. No other scheme or URL normalization is attempted.
    """
    if (
        not auth_token
        or not signature
        or not isinstance(params, Mapping)
        or not _valid_canonical_url(canonical_url, websocket=websocket)
    ):
        return False

    validator = RequestValidator(auth_token)
    candidates = (
        (canonical_url, f"{canonical_url}/")
        if websocket and not canonical_url.endswith("/")
        else (canonical_url,)
    )
    return any(validator.validate(candidate, params, signature) for candidate in candidates)


def _decode_message(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("Invalid Twilio Media Stream handshake") from None
    if not isinstance(value, dict):
        raise ValueError("Invalid Twilio Media Stream handshake")
    return value


async def read_twilio_start(
    websocket: Any,
    *,
    account_sid: str,
    expected_call_sid: str | None,
    run_id: str,
    correlation_id: str,
    expected_stream_sid: str | None = None,
    timeout_secs: float = 5,
) -> tuple[str, str]:
    """Read and validate Twilio's connected and start messages as one deadline."""
    if not math.isfinite(timeout_secs) or timeout_secs <= 0:
        raise ValueError("Twilio handshake timeout must be finite and positive")
    try:
        async with asyncio.timeout(timeout_secs):
            connected = _decode_message(await websocket.receive_text())
            if connected != {"event": "connected", "protocol": "Call", "version": "1.0.0"}:
                raise ValueError("Invalid Twilio Media Stream handshake")

            message = _decode_message(await websocket.receive_text())
            start = message.get("start")
            if not isinstance(start, dict):
                raise ValueError("Invalid Twilio Media Stream handshake")

            call_sid = start.get("callSid")
            inner_stream_sid = start.get("streamSid")
            stream_sid = message.get("streamSid")
            media_format = start.get("mediaFormat")
            custom = start.get("customParameters")
            valid = (
                message.get("event") == "start"
                and isinstance(account_sid, str)
                and _ACCOUNT_SID.fullmatch(account_sid) is not None
                and start.get("accountSid") == account_sid
                and isinstance(call_sid, str)
                and _CALL_SID.fullmatch(call_sid) is not None
                and (expected_call_sid is None or call_sid == expected_call_sid)
                and isinstance(stream_sid, str)
                and _STREAM_SID.fullmatch(stream_sid) is not None
                and inner_stream_sid == stream_sid
                and (expected_stream_sid is None or stream_sid == expected_stream_sid)
                and media_format == {"encoding": "audio/x-mulaw", "sampleRate": 8000, "channels": 1}
                and custom == {"run_id": run_id, "correlation_id": correlation_id}
            )
            if not valid:
                raise ValueError("Invalid Twilio Media Stream identity or format")
            return call_sid, stream_sid
    except TimeoutError:
        raise TimeoutError("Timed out waiting for Twilio Media Stream handshake") from None
