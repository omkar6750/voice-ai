import json
from datetime import UTC, datetime

import pytest
from voice_runtime.contracts.evidence import EvidenceBatch
from voice_runtime.diagnostics import (
    exception_diagnostic,
    provider_error_diagnostic,
    provider_exception_diagnostic,
    text_error_diagnostic,
)
from voice_runtime.execution.exchange import ExchangeTracker


class MemorySink:
    def __init__(self):
        self.records = []

    def submit(self, record):
        self.records.append(record)


def test_provider_quota_diagnostic_uses_fixed_code_and_discards_detail():
    diagnostic = provider_error_diagnostic(
        provider="groq",
        status_code=429,
        body={
            "error": {
                "code": "billing_hard_limit",
                "message": "API key sk-secret credits exhausted",
            }
        },
        request_id="req-123",
    )

    assert diagnostic["category"] == "provider_quota_exhausted"
    assert diagnostic["code"] == "provider_quota_exhausted"
    assert diagnostic["retryable"] is False
    assert diagnostic["detail"] is None
    assert diagnostic["provider_request_id"] is None


def test_provider_throttle_diagnostic_preserves_retry_delay():
    diagnostic = provider_error_diagnostic(
        provider="cartesia",
        status_code=429,
        body={"error": {"code": "rate_limit", "message": "Too many requests"}},
        retry_after_seconds=12,
    )

    assert diagnostic["category"] == "provider_rate_limit"
    assert diagnostic["retryable"] is True
    assert diagnostic["retry_after_seconds"] == 12


def test_pipeline_provider_text_is_not_collapsed_to_generic_pipeline_error():
    diagnostic = text_error_diagnostic("Groq TPM usage reached; request throttled")

    assert diagnostic["category"] == "provider_rate_limit"
    assert diagnostic["source"] == "provider"
    assert diagnostic["metadata"]["provider"] == "groq"
    assert diagnostic["retryable"] is True


def test_groq_failed_generation_and_request_id_are_discarded():
    class Response:
        status_code = 400

        @property
        def headers(self):
            return {"x-request-id": "groq-req-1", "retry-after": "2"}

        @staticmethod
        def json():
            return {
                "error": {
                    "code": "tool_use_failed",
                    "message": "Failed to call a function",
                    "failed_generation": '{"name":"change_node","arguments":',
                }
            }

    class ProviderError(Exception):
        response = Response()

    diagnostic = provider_exception_diagnostic(
        ProviderError("invalid tool call"), provider="groq", operation="llm"
    )

    assert diagnostic["source"] == "provider"
    assert diagnostic["category"] == "provider_request_failed"
    assert diagnostic["provider_request_id"] is None
    assert diagnostic["http_status"] == 400
    assert "failed_generation" not in diagnostic["metadata"]
    assert diagnostic["code"] == "provider_request_failed"
    assert diagnostic["metadata"]["operation"] == "llm"


def test_runtime_diagnostic_is_valid_evidence_and_keeps_timestamp_contract():
    sink = MemorySink()
    tracker = ExchangeTracker("run-1", sink)
    occurred_at = datetime.now(UTC)
    tracker.diagnostic(
        diagnostic_id="diagnostic-1",
        severity="warning",
        category="modem_signal",
        source="modem",
        code="low_signal_observed",
        message="Low modem signal was observed",
        uncertain=True,
        metadata={"rssi": 3},
    )

    records = EvidenceBatch(records=sink.records).records
    assert records[0].kind == "diagnostic"
    assert records[0].diagnostic_id == "diagnostic-1"
    assert records[0].uncertain is True
    assert records[0].metadata["rssi"] == 3
    assert records[0].timestamp_ns > 0
    assert (
        abs(records[0].timestamp_ns - int(occurred_at.timestamp() * 1_000_000_000)) < 1_000_000_000
    )


def test_exception_diagnostic_progress_envelope_is_adapted_before_spool_submission():
    sink = MemorySink()
    tracker = ExchangeTracker("run-1", sink)
    diagnostic = exception_diagnostic(
        ValueError("Transition is not allowed"),
        category="tool_failure",
        code="tool_error",
        message="Tool change_node failed",
    )

    tracker.diagnostic(**diagnostic)
    records = EvidenceBatch(records=sink.records).records

    assert len(records) == 1
    assert records[0].kind == "diagnostic"
    assert records[0].diagnostic_id == diagnostic["diagnostic_id"]
    assert records[0].timestamp_ns > 0
    assert "occurred_at" not in sink.records[0]


PRIVATE = "unknown-secret-Z73 +919876543210 private-query private-prompt private-transcript private-tool-args https://vendor.invalid/?credential=canary"


@pytest.mark.parametrize(
    "status,category",
    [
        (400, "provider_request_failed"),
        (401, "provider_authentication"),
        (429, "provider_rate_limit"),
        (503, "provider_unavailable"),
    ],
)
def test_provider_failure_payloads_cannot_enter_persisted_diagnostics(status, category):
    diagnostic = provider_error_diagnostic(
        provider=PRIVATE,
        status_code=status,
        body={"error": {"message": PRIVATE, "code": PRIVATE, "failed_generation": PRIVATE}},
        request_id=PRIVATE,
    )
    sink = MemorySink()
    tracker = ExchangeTracker("run-1", sink)
    tracker.diagnostic(**diagnostic)
    serialized = json.dumps(sink.records)
    assert PRIVATE not in serialized
    assert "unknown-secret-Z73" not in serialized
    assert "vendor.invalid" not in serialized
    assert diagnostic["category"] == category
    assert diagnostic["detail"] is None
    assert diagnostic["provider_request_id"] is None
    assert diagnostic["metadata"] == {"provider": "provider"}


def test_exception_diagnostics_never_stringify_errors_or_metadata_objects():
    class Poison(RuntimeError):
        def __str__(self):
            raise AssertionError("exception text was accessed")

    exc = Poison(PRIVATE)
    for diagnostic in (
        exception_diagnostic(exc, source=PRIVATE, category=PRIVATE, code=PRIVATE, message=PRIVATE),
        provider_exception_diagnostic(exc, provider=PRIVATE, operation=PRIVATE),
        text_error_diagnostic(exc, fallback_source=PRIVATE),
        provider_error_diagnostic(
            provider="groq", body={"error": {"message": exc, "code": exc}}, retry_after_seconds=exc
        ),
    ):
        assert diagnostic["detail"] is None
        assert "unknown-secret-Z73" not in json.dumps(diagnostic)
    assert exception_diagnostic(exc)["metadata"]["error_category"] == "runtime"


@pytest.mark.parametrize(
    "hint,category",
    [
        ("Groq TPM rate limit", "provider_rate_limit"),
        ("Groq credits exhausted", "provider_quota_exhausted"),
        ("Groq invalid key authentication", "provider_authentication"),
        ("", "pipeline_failure"),
    ],
)
def test_text_errors_keep_only_fixed_categories(hint, category):
    diagnostic = text_error_diagnostic(hint + " " + PRIVATE)
    assert diagnostic["category"] == category
    assert diagnostic["detail"] is None
    assert "unknown-secret-Z73" not in json.dumps(diagnostic)
    assert "vendor.invalid" not in json.dumps(diagnostic)
