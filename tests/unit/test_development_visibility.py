import io
import json
import logging
from typing import ClassVar

from voice_shared import dev_visibility


def test_dev_preserves_payloads_and_redacts_only_api_keys(monkeypatch):
    monkeypatch.setenv("VOICE_ENV", "dev")
    from voice_shared.logging import redact

    dev_visibility.register_api_keys(["canary-provider-key"])
    payload = {
        "api_key": "canary-provider-key",
        "authorization": "Bearer canary-provider-key",
        "message": "invalid codec; key=canary-provider-key",
        "prompt": "hello",
        "transcript": "caller speaking",
        "email": "caller@example.com",
        "config": {"credential_id": "abc"},
    }
    result = redact(payload)
    assert "canary-provider-key" not in json.dumps(result)
    assert result["prompt"] == "hello"
    assert result["email"] == "caller@example.com"
    assert result["message"] == "invalid codec; key=[REDACTED]"
    assert result["config"]["credential_id"] == "abc"
    assert "unknown-value" not in json.dumps(
        dev_visibility.redact_api_keys({"x-api-key": "unknown-value"})
    )
    assert "other-key" not in dev_visibility.redact_api_keys("api_key=other-key")


def test_dev_redacts_runtime_and_oauth_credentials_without_hiding_identifiers():
    payload = {
        "x-voice-runtime-token": "runtime-secret",
        "refresh_token": "oauth-secret",
        "password": "database-secret",
        "cookie": "session-secret",
        "token_id": "token-record-id",
        "credential_id": "credential-record-id",
    }
    result = dev_visibility.redact_api_keys(payload)
    for field in ("x-voice-runtime-token", "refresh_token", "password", "cookie"):
        assert result[field] == "[REDACTED]"
    assert result["token_id"] == "token-record-id"
    assert result["credential_id"] == "credential-record-id"


def test_dev_retains_raw_provider_error_and_request_id(monkeypatch):
    monkeypatch.setenv("VOICE_ENV", "dev")
    from voice_runtime.diagnostics import provider_exception_diagnostic

    class Response:
        status_code = 400
        headers: ClassVar = {"x-request-id": "req-123"}

        def json(self):
            return {
                "error": {
                    "message": "Invalid audio format",
                    "code": "invalid_audio",
                    "api_key": "never-visible",
                }
            }

    class Error(Exception):
        response = Response()

    result = provider_exception_diagnostic(
        Error("Invalid audio format"), provider="sarvam", operation="stt"
    )
    assert result["detail"] == "Invalid audio format"
    assert result["provider_request_id"] == "req-123"
    assert result["metadata"]["provider_error"]["error"]["code"] == "invalid_audio"
    assert "never-visible" not in json.dumps(result)


def test_dev_sdk_log_keeps_message_and_redacts_key(monkeypatch):
    dev_visibility.register_api_keys(["canary-provider-key"])
    monkeypatch.setenv("VOICE_ENV", "dev")
    from voice_runtime.safe_logs import _patch_loguru, _safe_record_factory, _sink

    record = {
        "extra": {},
        "message": "provider error canary-provider-key",
        "module": "vendor",
        "function": "receive",
        "line": 42,
        "exception": None,
        "level": type("Level", (), {"name": "ERROR"})(),
    }
    _patch_loguru(record)

    class Message:
        pass

    message = Message()
    message.record = record
    output = io.StringIO()
    _sink(output)(message)
    result = json.loads(output.getvalue())
    assert result["message"] == "provider error [REDACTED]"
    assert result["event"] == "sdk_log"
    record = _safe_record_factory(
        "vendor", logging.ERROR, "file.py", 1, "invalid %s", ("codec",), None
    )
    assert record.getMessage() == "invalid codec"


def test_production_keeps_existing_redaction(monkeypatch):
    monkeypatch.setenv("VOICE_ENV", "prod")
    from voice_runtime.diagnostics import provider_error_diagnostic
    from voice_shared.logging import redact

    assert redact({"message": "private", "prompt": "private"}) == {
        "message": "[redacted]",
        "prompt": "[redacted]",
    }
    result = provider_error_diagnostic(
        provider="sarvam", status_code=400, body={"message": "private"}
    )
    assert result["detail"] is None
    assert "provider_error" not in result["metadata"]


def test_dev_run_identifiers_and_long_errors_are_retained(monkeypatch):
    monkeypatch.setenv("VOICE_ENV", "dev")
    from voice_runtime.diagnostics import text_error_diagnostic
    from voice_runtime.safe_logs import safe_event_payload
    from voice_shared.request_evidence import json_payload

    run_id = "c8d28cc2-78ed-4f1e-b2a3-19839777a348"
    assert safe_event_payload("provider_error", run_id=run_id)["run_id"] == run_id
    raw = "sarvam error " + "x" * 4000
    diagnostic = text_error_diagnostic(raw)
    assert diagnostic["metadata"]["raw_error"] == raw
    assert json_payload(json.dumps({"run_id": run_id}).encode())["run_id"] == run_id
