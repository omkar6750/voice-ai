from datetime import UTC, datetime

from voice_runtime.contracts.evidence import EvidenceBatch
from voice_runtime.diagnostics import (
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


def test_provider_quota_diagnostic_preserves_code_and_redacts_detail():
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
    assert diagnostic["code"] == "billing_hard_limit"
    assert diagnostic["retryable"] is False
    assert "sk-secret" not in diagnostic["detail"]
    assert diagnostic["provider_request_id"] == "req-123"


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


def test_groq_failed_generation_is_preserved_as_provider_diagnostic_metadata():
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
    assert diagnostic["provider_request_id"] == "groq-req-1"
    assert diagnostic["http_status"] == 400
    assert diagnostic["metadata"]["failed_generation"] == '{"name":"change_node","arguments":'
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
    assert records[0].timestamp_ns > int(occurred_at.timestamp() * 1_000_000_000)
