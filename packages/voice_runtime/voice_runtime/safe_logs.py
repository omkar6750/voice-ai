"""Allowlisted operational logs, separate from access-controlled run evidence.

Call configure_safe_logging() at process startup BEFORE importing Pipecat/vendor
modules. It replaces existing stdlib and Loguru sinks. Do not add raw sinks later.
No message, exception, traceback, processor name, or vendor extra is a safe field.
"""

from __future__ import annotations

import json
import logging
import math
import sys
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from loguru import logger
from voice_shared.dev_visibility import is_development, redact_api_keys


class RuntimeEvent(StrEnum):
    PERF_TIMING = "perf_timing"
    API_REQUEST_FAILED = "api_request_failed"
    API_VALIDATION_FAILED = "api_validation_failed"
    CREDENTIALS_MISSING = "credentials_missing"
    PROVIDER_FAILED = "provider_failed"
    LLM_FALLBACK_ACTIVATED = "llm_fallback_activated"
    CLASSIFIER_FAILED = "classifier_failed"
    CLASSIFIER_INVALID = "classifier_invalid"
    INTEGRATION_FAILED = "integration_failed"
    INBOUND_CHECK_FAILED = "inbound_check_failed"
    MESSAGE_STARTED = "message_started"
    MESSAGE_ACCEPTED = "message_accepted"
    MESSAGE_FAILED = "message_failed"
    RECIPIENT_MISSING = "recipient_missing"
    CALLBACK_INVALID = "callback_invalid"
    CALLBACK_CREATED = "callback_created"
    CALLBACK_FAILED = "callback_failed"
    RETRIEVAL_FAILED = "retrieval_failed"
    TOOL_FAILED = "tool_failed"
    EVIDENCE_FAILED = "evidence_failed"
    PIPELINE_FAILED = "pipeline_failed"
    CALL_FAILED = "call_failed"
    PCM_CONFIGURED = "pcm_configured"
    PCM_OPENED = "pcm_opened"
    PCM_READ_FAILED = "pcm_read_failed"
    PCM_WRITE_FAILED = "pcm_write_failed"
    PCM_IO_SUMMARY = "pcm_io_summary"
    PCM_CAPTURED = "pcm_captured"
    CAPTURE_CLOSED = "capture_closed"
    FRAME_OBSERVED = "frame_observed"
    MODEM_COMMAND = "modem_command"
    MODEM_RESPONSE = "modem_response"


_MARKS = frozenset(
    {
        "llm_started",
        "llm_ended",
        "tts_started",
        "tts_stopped",
        "stt_final",
        "stt_missing_final",
        "vad_speech_started",
        "vad_speech_stopped",
        "caller_started",
        "caller_stopped",
        "playback_started",
        "playback_stopped",
        "interrupted",
        "provider_error",
        "user_turn_started",
        "user_turn_stopped",
        "user_turn_stop_timeout",
    }
)
_TOKEN = object()
_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


def error_category(exc: BaseException) -> str:
    """Classify without reading exception text, attributes, or a custom class name."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, PermissionError):
        return "permission"
    if isinstance(exc, ConnectionError):
        return "connection"
    if isinstance(exc, OSError):
        return "io"
    if isinstance(exc, (ValueError, TypeError)):
        return "validation"
    return "runtime"


def opaque_id(value) -> UUID | None:
    if type(value) is UUID:
        return value
    if type(value) is str and len(value) in {32, 36}:
        try:
            parsed = UUID(value)
        except ValueError:
            return None
        if value.lower() in {str(parsed), parsed.hex}:
            return parsed
    return None


def safe_event_payload(event: RuntimeEvent | str, **fields) -> dict:
    """Only fixed event names and field-specific primitive values cross this boundary."""
    if is_development():
        return redact_api_keys(
            {"event": event.value if isinstance(event, RuntimeEvent) else event, **fields}
        )
    if type(event) is RuntimeEvent:
        name = event.value
    elif type(event) is str and event in _MARKS:
        name = event
    else:
        name = "untrusted_log"
    result = {"event": name}
    if name == "untrusted_log":
        return result
    choices = {
        "component": {
            "api",
            "clerk",
            "membership",
            "db",
            "loop",
            "sim_rx",
            "sim_tx",
            "modem",
            "capture",
            "browser_audio",
            "evidence",
        },
        "phase": {
            "request",
            "verify",
            "lookup",
            "query",
            "lag",
            "read",
            "write",
            "flush",
            "gap",
            "frame",
            "batch",
        },
        "transport": {"none", "browser", "sim7600"},
        "route_group": {
            "health",
            "auth",
            "runs",
            "calls",
            "browser-sessions",
            "agents",
            "knowledge",
            "integrations",
            "tools",
            "contacts",
            "callbacks",
            "settings",
            "providers",
            "platform",
            "orgs",
            "other",
        },
        "provider": {"groq", "gemini", "cartesia", "sarvam", "jev", "whatsapp"},
        "operation": {"llm", "stt", "tts"},
        "status": {
            "started",
            "accepted",
            "completed",
            "failed",
            "cancelled",
            "interrupted",
            "ok",
            "error",
            "unknown",
        },
        "error_category": {"timeout", "permission", "connection", "io", "validation", "runtime"},
        "direction": {"input", "output", "UPSTREAM", "DOWNSTREAM"},
        "response": {"ok", "rejected", "data"},
        "validation_scope": {
            "request_query",
            "request_path",
            "request_header",
            "request_body",
            "model_validation",
            "internal",
        },
        "validation_field": {
            "items",
            "total_count",
            "next_offset",
            "stale",
            "checked_at",
            "label",
            "valid",
            "is_free_tier",
            "limit_remaining",
            "usage_daily",
            "usage_monthly",
            "credits_total",
            "credits_usage",
            "free_model_daily_requests",
            "error_category",
            "slots",
            "source",
            "modality",
            "context_length",
            "max_completion_tokens",
            "is_free",
            "account_available",
            "runtime_supported",
            "compatibility_reason",
            "endpoint_providers",
            "provider_name",
            "tag",
            "quantization",
            "uptime_last_30m",
            "latency_last_30m",
            "throughput_last_30m",
            "limit",
            "offset",
            "free_only",
            "q",
            "author",
            "tool_calling",
            "structured_output",
            "reasoning",
            "min_context",
            "max_prompt_price",
            "credential_id",
            "org_id",
            "data",
            "links",
            "id",
            "name",
            "pricing",
            "prompt",
            "completion",
            "request",
            "image",
            "architecture",
            "input_modalities",
            "output_modalities",
            "supported_parameters",
        },
        "request_method": {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"},
        "validation_detail_state": {"available", "empty", "unavailable"},
        "validation_error_type": {
            "missing",
            "string_type",
            "extra_forbidden",
            "int_parsing",
            "float_parsing",
            "decimal_parsing",
            "bool_parsing",
            "list_type",
            "dict_type",
            "model_type",
            "enum",
            "greater_than_equal",
            "less_than_equal",
            "string_too_long",
            "string_too_short",
            "literal_error",
        },
    }
    for key, allowed in choices.items():
        value = fields.get(key)
        if type(value) is str and value in allowed:
            result[key] = value
    for key in ("bytes", "samples", "count", "sample_rate", "http_status", "at_ms"):
        value = fields.get(key)
        if type(value) is int and 0 <= value <= 2**53:
            if key != "http_status" or 100 <= value <= 599:
                result[key] = value
    for key in ("at_command", "at_response_line"):
        value = fields.get(key)
        if type(value) is str and len(value) <= 240:
            # These fields are emitted only by the modem adapter after its
            # command allowlist and identifier scrubber have run. Keep them
            # separate from arbitrary vendor messages and exceptions.
            if key == "at_command" and _safe_at_command(value):
                result[key] = value
            elif key == "at_response_line" and _safe_at_line(value):
                result[key] = value
    value = fields.get("duration_ms")
    if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86400000:
        result["duration_ms"] = round(value, 4)
    # Accept UUID objects only: phone numbers, URL IDs, and arbitrary strings are
    # not opaque identifiers. Callers must never pass provider IDs here.
    for key in ("run_id", "operation_id", "callback_id"):
        value = fields.get(key)
        if type(value) is UUID:
            result[key] = value.hex
    return result


def _safe_at_command(value: str) -> bool:
    import re

    return bool(
        re.fullmatch(
            r"AT(?:\+?(?:CPIN\?|CSQ|CEREG\?|CREG\?|CGATT\?|COPS\?|CPSI\?|CGACT\?|CLCC|CPCMREG\?|CPCMFRM\?|CEER|CGMR)|I|A|ATH|\+CHUP|\+CPCMREG=[01]|\+CPCMFRM=[01])",
            value,
        )
        or value == "ATD<number>;"
    )


def _safe_at_line(value: str) -> bool:
    import re

    return bool(
        value in {"OK", "ERROR", "NO CARRIER", "BUSY", "NO ANSWER"}
        or re.fullmatch(
            r"\+(?:CPIN|CSQ|CEREG|CREG|CGATT|COPS|CPSI|CGACT|CLCC|CPCMREG|CPCMFRM|CEER): [A-Za-z0-9 _,.\-+<>\"']{1,210}",
            value,
        )
        or re.fullmatch(r"SIM7600|\d{1,3}(?:\.\d{1,3}){1,3}", value)
    )


def operational_event(event: RuntimeEvent, *, level: str = "INFO", **fields) -> None:
    payload = safe_event_payload(event, **fields)
    logger.bind(_operational_token=_TOKEN, _operational_payload=payload).log(
        level if type(level) is str and level in _LEVELS else "INFO",
        json.dumps(payload, separators=(",", ":")),
    )


def _patch_loguru(record: dict) -> None:
    extra = record["extra"]
    trusted = extra.get("_operational_token") is _TOKEN
    if is_development():
        payload = (
            extra.get("_operational_payload")
            if trusted
            else {
                "event": "sdk_log",
                "message": record["message"],
                "module": record["module"],
                "function": record["function"],
                "line": record["line"],
                "extra": extra,
            }
        )
        exception = record.get("exception")
        if exception:
            import traceback

            payload = {
                **payload,
                "exception": "".join(
                    traceback.format_exception(exception.type, exception.value, exception.traceback)
                ),
            }
        payload = redact_api_keys(payload)
        record["message"] = json.dumps(payload, separators=(",", ":"), default=str)
        record["exception"] = None
        record["extra"] = {"_operational_token": _TOKEN, "_operational_payload": payload}
        return
    if trusted:
        payload = extra["_operational_payload"]
    else:
        payload = {"event": "untrusted_log"}
    # Never let Loguru's exception renderer inspect locals or SDK exception text.
    record["message"] = json.dumps(payload, separators=(",", ":"))
    record["exception"] = None
    record["extra"] = (
        {"_operational_token": _TOKEN, "_operational_payload": payload} if trusted else {}
    )


_event_sink = None


def set_event_sink(sink):
    global _event_sink
    _event_sink = sink


def _sink(stream):
    def write(message):
        record = message.record
        extra = record["extra"]
        payload = (
            extra.get("_operational_payload", {})
            if extra.get("_operational_token") is _TOKEN
            else {}
        )
        severity = record["level"].name
        if not payload and severity in {"DEBUG", "INFO"}:
            # Pipecat/provider DEBUG and INFO records contain unrestricted
            # text. Drop them instead of printing a flood of useless markers;
            # operator-facing facts use operational_event() below.
            return
        event = payload.get("event")
        try:
            event = RuntimeEvent(event) if type(event) is str else None
        except ValueError:
            event = event if type(event) is str and event in _MARKS else None
        fields = {key: value for key, value in payload.items() if key != "event"}
        if is_development():
            event = payload.get("event", "sdk_log")
        # UUIDs were canonicalized by the helper; restore their typed identity.
        for key in ("run_id", "operation_id", "callback_id"):
            value = fields.get(key)
            if type(value) is str and len(value) == 32:
                try:
                    fields[key] = UUID(hex=value)
                except ValueError:
                    fields.pop(key, None)
        safe = safe_event_payload(event, **fields)
        safe["level"] = severity if severity in _LEVELS else "INFO"
        if _event_sink is not None:
            _event_sink(safe)
        else:
            stream.write(json.dumps(safe, separators=(",", ":")) + "\n")
            stream.flush()

    return write


class _SafeStandardHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        # Ignore even forged 'safe' extras. SDK log severity remains observable.
        level = record.levelname if record.levelname in _LEVELS else "INFO"
        logger.log(level, record.getMessage() if is_development() else "")


def _safe_record_factory(
    name, level, pathname, lineno, msg, args, exc_info, func=None, sinfo=None, **kwargs
):
    # Sanitize BEFORE any handler/formatter (including a subsequently installed
    # server capture handler) can stringify an SDK message or exception.
    if is_development():
        record = logging.LogRecord(name, level, pathname, lineno, msg, args, exc_info, func, sinfo)
        message = record.getMessage()
        if exc_info:
            import traceback

            message += "\n" + "".join(traceback.format_exception(*exc_info))
        record.msg = redact_api_keys(message)
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        return record
    safe_level = level if type(level) is int and level in {10, 20, 30, 40, 50} else 20
    return logging.LogRecord(
        "runtime.sdk",
        safe_level,
        __file__,
        0,
        '{"event":"untrusted_log"}',
        (),
        None,
    )


class _OwnedFileSink:
    def __init__(self, path):
        self.stream = Path(path).open("a", encoding="utf-8")
        self.write = _sink(self.stream)

    def stop(self):
        self.stream.close()


def configure_safe_logging(
    *, console=None, pipeline_path=None, level: str = "INFO", env_files=()
) -> None:
    """Install process-wide operational sinks. Safe to call again at startup.

    Development retains SDK messages with API keys removed. Production records
    retain severity only; application facts must use
    operational_event(). A pipeline file gets the identical safe Loguru payload.
    EvidenceObserver's per-run file uses safe_event_payload() separately.
    """
    import os

    from dotenv import dotenv_values
    from voice_shared.dev_visibility import configure as configure_visibility

    values = {}
    for env_file in env_files:
        values.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    values.update(os.environ)
    configure_visibility(
        values.get("VOICE_ENV", "dev"),
        [
            value
            for key, value in values.items()
            if key.endswith("_API_KEY")
            or key.endswith("_SERVICE_TOKEN")
            or key == "VOICE_INTEGRATION_KEYS"
        ],
    )
    if is_development():
        level = "DEBUG"
    stream = console if console is not None else sys.stderr
    logger.remove()
    logger.configure(patcher=_patch_loguru)
    safe_level = level if type(level) is str and level in _LEVELS else "INFO"
    logger.add(
        _sink(stream),
        format="{message}",
        level=safe_level,
        backtrace=False,
        diagnose=False,
        catch=False,
    )
    if pipeline_path is not None:
        logger.add(
            _OwnedFileSink(pipeline_path),
            format="{message}",
            level=safe_level,
            backtrace=False,
            diagnose=False,
            catch=False,
        )
    root = logging.getLogger()
    logging.setLogRecordFactory(_safe_record_factory)
    root.handlers[:] = [_SafeStandardHandler()]
    root.setLevel(safe_level)
    for entry in logging.Logger.manager.loggerDict.values():
        if isinstance(entry, logging.Logger):
            entry.handlers.clear()
            entry.propagate = True
