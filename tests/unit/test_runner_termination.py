"""Native call outcomes reach control reporting only after transport release."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from voice_runtime.execution.runner import apply_transport_outcome, execute_call
from voice_runtime.execution.termination import CallTermination


async def run_driver(tmp_path, state, *, cleanup_error=None, call_outcome=None):
    requests = []
    driver = SimpleNamespace(
        prepare=AsyncMock(),
        call=AsyncMock(return_value=state),
        close=AsyncMock(),
        call_outcome=call_outcome,
    )
    driver.close.side_effect = cleanup_error

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

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://test"
    ) as client:
        if cleanup_error:
            with pytest.raises(RuntimeError, match="manual reconciliation"):
                await execute_call(client, "fake-token", "run-1", "ep-1", driver, tmp_path / "spool")
            assert not any(body.get("transport_released") for _, body in requests)
            return None, requests
        outcome = await execute_call(
            client, "fake-token", "run-1", "ep-1", driver, tmp_path / "spool"
        )
    driver.call.assert_awaited_once_with("+15551234567")
    return outcome, requests


@pytest.mark.parametrize(
    ("cause", "outcome"),
    [
        ("agent_hangup", "completed"),
        ("terminal_completed", "completed"),
        ("caller_hangup", "failed"),
        ("disconnect_unknown", "failed"),
        ("pipeline_failure", "failed"),
        ("network_failure", "failed"),
        ("caller_idle_timeout", "failed"),
        ("duration_limit", "failed"),
    ],
)
async def test_typed_outcome_survives_transport_cleanup(tmp_path, cause, outcome):
    termination = CallTermination()
    termination.request(cause, graceful=cause in {"agent_hangup", "terminal_completed"})
    termination.pipeline_finished()
    state = {"flow_node": "closing", "termination": termination.snapshot()}
    result, requests = await run_driver(tmp_path, state)
    assert result == outcome
    final = requests[-1][1]
    assert final["status"] == outcome
    reported = final["final_state"]["runtime"]["termination"]
    assert reported["cause"] == cause
    assert reported["cleanup_status"] == "confirmed"
    assert state["termination"]["cleanup_status"] == "unknown"
    assert final["final_state"]["evidence_incomplete"] is False
    if outcome == "failed":
        assert final["diagnostics"][0]["code"] == cause


async def test_agent_intent_without_finished_pipeline_is_not_completion(tmp_path):
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    result, requests = await run_driver(tmp_path, {"termination": call.snapshot()})
    assert result == "failed"
    assert requests[-1][1]["status"] == "failed"


async def test_invalid_termination_cannot_fall_back_to_completed(tmp_path):
    result, requests = await run_driver(tmp_path, {"termination": {"cause": "made_up"}})
    assert result == "failed"
    assert requests[-1][1]["diagnostics"][0]["code"] == "call_execution_failed"


async def test_driver_without_new_termination_contract_keeps_existing_behavior(tmp_path):
    result, requests = await run_driver(tmp_path, {"legacy_result": "ok"})
    assert result == "completed"
    assert requests[-1][1]["final_state"]["runtime"] == {"legacy_result": "ok"}


def test_modem_release_evidence_updates_unknown_call_outcome():
    termination = CallTermination()
    termination.request("disconnect_unknown")
    termination.pipeline_finished()
    state = {"termination": termination.snapshot()}
    evidence = {
        "reason": "remote_hangup",
        "confidence": "high",
        "registration": {"voice_registered": True, "rssi": 15},
        "events": [{"signal": "NO CARRIER"}],
    }
    diagnostics = [
        {
            "category": "call_termination",
            "code": "disconnect_unknown",
            "uncertain": True,
        }
    ]
    final_state, reason = apply_transport_outcome(state, evidence, diagnostics)
    reported = final_state["termination"]
    assert reason == "remote_hangup"
    assert reported["cause"] == "remote_hangup"
    assert reported["transport_evidence"] == evidence
    assert diagnostics[0]["code"] == "remote_hangup"
    assert diagnostics[0]["uncertain"] is False


def test_transport_disconnect_evidence_does_not_hide_pipeline_failure():
    final_state, reason = apply_transport_outcome(
        {"termination": {"cause": "pipeline_failure"}},
        {"reason": "remote_hangup", "confidence": "high"},
        [],
    )
    assert reason is None
    assert final_state["termination"]["cause"] == "pipeline_failure"


async def test_uncertain_transport_remains_reserved_without_final_success(tmp_path):
    call = CallTermination()
    call.request("agent_hangup", graceful=True)
    call.pipeline_finished()
    await run_driver(
        tmp_path, {"termination": call.snapshot()}, cleanup_error=RuntimeError("modem active")
    )
