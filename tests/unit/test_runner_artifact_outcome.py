"""Artifact registration failures do not rewrite the call's known outcome."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from voice_runtime.execution.runner import execute_call
from voice_runtime.execution.termination import CallTermination


@pytest.mark.parametrize(
    ("cause", "expected_status", "expected_error"),
    [
        ("terminal_completed", "completed", None),
        (
            "pipeline_failure",
            "failed",
            "Call ended without flow completion: pipeline_failure",
        ),
    ],
)
async def test_artifact_registration_failure_preserves_call_outcome(
    tmp_path, cause, expected_status, expected_error
):
    termination = CallTermination()
    termination.request(cause, graceful=cause == "terminal_completed")
    termination.pipeline_finished()
    state = {"flow_node": "closing", "termination": termination.snapshot()}
    requests = []
    driver = SimpleNamespace(
        prepare=AsyncMock(), call=AsyncMock(return_value=state), close=AsyncMock()
    )

    async def respond(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith("claim"):
            return httpx.Response(
                200,
                json={
                    "status": "claimed",
                    "destination": "+15551234567",
                    "resolved_config": {"call_limits": {"max_duration_secs": 15}},
                },
            )
        if body.get("transport_released"):
            driver.close.assert_awaited_once()
        return httpx.Response(200, json={"status": "ok"})

    async def fail_artifact_registration():
        raise RuntimeError("artifact store unavailable")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://test"
    ) as client:
        result = await execute_call(
            client,
            "fake-token",
            "run-1",
            "ep-1",
            driver,
            tmp_path / "spool",
            after_close=fail_artifact_registration,
        )

    driver.call.assert_awaited_once_with("+15551234567")
    terminal = requests[-1][1]
    assert result == expected_status
    assert terminal["status"] == expected_status
    assert terminal["error"] == expected_error
    assert terminal["final_state"]["evidence_incomplete"] is True
    assert terminal["final_state"]["runtime"]["termination"]["cause"] == cause
    assert any(item["code"] == "artifact_registration_failed" for item in terminal["diagnostics"])
