from unittest.mock import AsyncMock

import httpx
import pytest
from voice_api.services import runtime_readiness as module


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("health", "status", "body", "state", "code"),
    [
        (502, 200, {}, "starting", None),
        (200, 401, {}, "unavailable", "runtime_authentication_failed"),
        (200, 503, {}, "starting", None),
        (200, 200, {"boot_id": "boot", "blocked": True}, "busy", "runtime_busy"),
        (200, 200, {"boot_id": "boot", "admission_available": False}, "busy", "runtime_busy"),
        (
            200,
            200,
            {"boot_id": "boot", "admission_enabled": False},
            "unavailable",
            "runtime_admission_disabled",
        ),
        (200, 200, {"boot_id": "boot"}, "ready", None),
        (200, 200, {}, "unavailable", "runtime_status_invalid"),
    ],
)
async def test_probe_is_bounded_read_only_and_returns_safe_state(
    monkeypatch, health, status, body, state, code
):
    client = AsyncMock()
    client.get.side_effect = [httpx.Response(health), httpx.Response(status, json=body)]
    monkeypatch.setattr(module, "client", lambda: client)
    result = await module.runtime_readiness()
    assert (result.state, result.code) == (state, code)
    assert all(call.kwargs["timeout"] == 2 for call in client.get.call_args_list)
    client.post.assert_not_called()
    assert "boot" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_connection_timeout_is_starting(monkeypatch):
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectTimeout("private upstream address")
    monkeypatch.setattr(module, "client", lambda: client)
    result = await module.runtime_readiness()
    assert result.state == "starting"
    assert "private" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_ambiguous_mutation_is_not_retried(monkeypatch):
    from fastapi import HTTPException
    from voice_api.services import runtime_dispatch

    runtime = AsyncMock()
    runtime.post.side_effect = httpx.ReadTimeout("may already have accepted")
    monkeypatch.setattr(runtime_dispatch, "client", lambda: runtime)
    with pytest.raises(HTTPException) as error:
        await runtime_dispatch.control("/v1/sessions", {})
    assert error.value.detail["code"] == "runtime_execution_uncertain"
    assert error.value.detail["diagnostic_id"]
    runtime.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_restart_after_ready_is_rejected_before_dispatch(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        module,
        "runtime_readiness",
        AsyncMock(return_value=module.RuntimeReadiness(state="starting")),
    )
    with pytest.raises(HTTPException) as error:
        await module.require_runtime_ready()
    assert error.value.detail["code"] == "runtime_starting"


@pytest.mark.asyncio
async def test_readiness_never_releases_uncertain_assignment(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException
    from voice_api.services import runtime_dispatch

    run = SimpleNamespace(id="run", status="queued")
    assignment = SimpleNamespace(state="uncertain")
    session = AsyncMock()
    session.get.side_effect = [run, assignment]
    probe = AsyncMock()
    monkeypatch.setattr(module, "require_runtime_ready", probe)
    with pytest.raises(HTTPException, match="reconciliation"):
        await runtime_dispatch.dispatch(session, run)
    probe.assert_not_awaited()
    session.commit.assert_not_awaited()
    assert assignment.state == "uncertain"
