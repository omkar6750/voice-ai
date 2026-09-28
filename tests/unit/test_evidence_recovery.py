from voice_runtime.execution.recovery import normalize_known_diagnostic


def test_recovery_removes_only_progress_timestamp_and_preserves_evidence_identity():
    record = {
        "id": "stable-record-id",
        "run_id": "run-id",
        "kind": "diagnostic",
        "diagnostic_id": "stable-diagnostic-id",
        "timestamp_ns": 123456789,
        "occurred_at": "2026-09-27T13:00:00Z",
        "severity": "error",
        "category": "tool_failure",
        "source": "runtime",
        "message": "Tool change_node failed",
    }

    normalized, corrected = normalize_known_diagnostic(record)

    assert corrected
    assert normalized["id"] == record["id"]
    assert normalized["diagnostic_id"] == record["diagnostic_id"]
    assert normalized["timestamp_ns"] == record["timestamp_ns"]
    assert "occurred_at" not in normalized
    assert "occurred_at" in record


def test_recovery_does_not_rewrite_other_event_shapes():
    record = {"kind": "message", "occurred_at": "not-an-evidence-field"}
    normalized, corrected = normalize_known_diagnostic(record)
    assert not corrected
    assert normalized is record
