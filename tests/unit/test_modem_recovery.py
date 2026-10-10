import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from voice_runner import modem_recovery
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.status import ModemStatus
from voice_shared.contracts import ModemRecovery, SessionIdentity


def setup_recovery(monkeypatch, *, active=False, task_running=False, generation_mismatch=False):
    run_id, generation, boot_id = uuid4(), uuid4(), uuid4()
    owner = SimpleNamespace(
        generation=str(uuid4() if generation_mismatch else generation),
        boot_id=str(boot_id),
        modem_ports={"com16", "com17"},
        request=SimpleNamespace(channel="sim7600"),
        state="uncertain",
        closed=asyncio.Event(),
        task=SimpleNamespace(done=lambda: not task_running),
    )
    owner.closed.set()
    manager = SimpleNamespace(
        settings=SimpleNamespace(local=True),
        sessions={str(run_id): owner},
        probe_ports=set(),
        lock=asyncio.Lock(),
    )
    body = ModemRecovery(
        at_port="COM16",
        audio_port="COM17",
        session=SessionIdentity(run_id=run_id, generation=generation, boot_id=boot_id),
    )
    calls = []

    class Modem:
        def __init__(self, *args, **kwargs):
            calls.append("open")

        async def probe_status(self):
            return ModemStatus(
                alive=True,
                serial_connected=True,
                active_call=active,
                call_state=CallState.ACTIVE if active else CallState.IDLE,
            )

        async def close(self):
            calls.append("close")

    monkeypatch.setattr(modem_recovery, "Sim7600Modem", Modem)
    monkeypatch.setattr(modem_recovery, "verify_audio_port", lambda body: calls.append("audio"))
    return manager, body, owner, calls


async def test_recovery_releases_stopped_owner_only_after_hardware_proof(monkeypatch):
    manager, body, owner, calls = setup_recovery(monkeypatch)
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert result["verified"] and owner.state == "ended"
    assert "audio" in calls and "close" in calls
    assert not manager.probe_ports


@pytest.mark.parametrize(
    "option,reason",
    [("task_running", "execution_active"), ("generation_mismatch", "identity_mismatch")],
)
async def test_recovery_does_not_touch_hardware_when_execution_is_unverified(
    monkeypatch, option, reason
):
    manager, body, owner, calls = setup_recovery(monkeypatch, **{option: True})
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert not result["verified"] and result["reason"] == reason
    assert not calls and owner.state == "uncertain"


async def test_active_modem_call_is_not_hung_up_or_released(monkeypatch):
    manager, body, owner, calls = setup_recovery(monkeypatch, active=True)
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert result["reason"] == "call_active"
    assert owner.state == "uncertain" and "audio" not in calls
    assert not manager.probe_ports


async def test_serial_failure_preserves_owner_and_releases_probe_reservation(monkeypatch):
    manager, body, owner, _ = setup_recovery(monkeypatch)

    def fail(body):
        raise OSError("audio port held by another process")

    monkeypatch.setattr(modem_recovery, "verify_audio_port", fail)
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert result["reason"] == "hardware_unavailable"
    assert owner.state == "uncertain" and not manager.probe_ports


async def test_runtime_restart_with_no_old_session_still_requires_hardware_proof(monkeypatch):
    manager, body, _, calls = setup_recovery(monkeypatch)
    manager.sessions.clear()
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert result["verified"] and "audio" in calls


async def test_other_uncertain_owner_cannot_be_released_using_the_wrong_run(monkeypatch):
    manager, body, owner, calls = setup_recovery(monkeypatch)
    manager.sessions = {str(uuid4()): owner}
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert result["reason"] == "execution_active" and not calls


async def test_modem_command_error_does_not_count_as_idle_proof(monkeypatch):
    manager, body, owner, calls = setup_recovery(monkeypatch)

    async def incomplete(self):
        return ModemStatus(
            alive=True,
            serial_connected=True,
            call_state=CallState.IDLE,
            last_error="AT+CLCC timed out",
        )

    monkeypatch.setattr(modem_recovery.Sim7600Modem, "probe_status", incomplete)
    result = await modem_recovery.verify_modem_recovery(manager, body)
    assert result["reason"] == "probe_failed"
    assert owner.state == "uncertain" and "audio" not in calls


@pytest.mark.parametrize("verified", [True, False])
async def test_api_recovery_updates_run_call_and_assignment_only_with_proof(monkeypatch, verified):
    from voice_api.api.v1.endpoints import remote_execution as api
    from voice_api.services import runtime_dispatch

    endpoint = SimpleNamespace(
        config={"at_port": "COM16", "audio_port": "COM17"}, status={}, last_seen_at=None
    )
    run = SimpleNamespace(
        id=str(uuid4()),
        org_id=str(uuid4()),
        status="uncertain",
        error="expired",
        final_state={},
        lease_expires_at=None,
    )
    assignment = SimpleNamespace(
        generation=str(uuid4()),
        boot_id=str(uuid4()),
        state="uncertain",
        lease_expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    call = SimpleNamespace(id=str(uuid4()), status="uncertain")

    class Database:
        sync_session = None
        committed = False

        def __init__(self):
            self.rows = iter([run, call, None])

        async def get(self, model, identity, **kwargs):
            return endpoint if model is api.RuntimeEndpoint else assignment

        async def scalar(self, query):
            return next(self.rows)

        async def commit(self):
            self.committed = True

    async def control(path, body):
        assert path == "/v1/modems/reconcile"
        assert body["session"]["generation"] == assignment.generation
        from dataclasses import asdict

        status = asdict(
            ModemStatus(
                alive=True,
                serial_connected=True,
                call_state=CallState.IDLE if verified else CallState.ACTIVE,
                active_call=not verified,
            )
        )
        status.pop("available_transports")
        status["call_state"] = status["call_state"].value
        return {
            "verified": verified,
            "reason": "idle_verified" if verified else "call_active",
            "message": "checked",
            "status": status,
        }

    monkeypatch.setattr(api, "bind_organization", lambda *args: None)
    monkeypatch.setattr(api, "require_local_modem", lambda: None)
    monkeypatch.setattr(runtime_dispatch, "control", control)
    database = Database()
    result = await api.recover(str(uuid4()), database)
    assert result["status"] == ("recovered" if verified else "blocked")
    assert run.status == call.status == ("failed" if verified else "uncertain")
    assert assignment.state == ("ended" if verified else "uncertain")
    assert database.committed
    assert not result.get("redialed", False)
    # Exercise the same strict serialization used for JSON storage and dashboard responses.
    from voice_api.schemas.execution import EndpointRecoveryResponse, EndpointStatus

    EndpointRecoveryResponse.model_validate(result)
    stored = EndpointStatus.model_validate(endpoint.status)
    assert stored.voice_registration_known is False


def test_status_contract_keeps_historical_records_and_rejects_malformed_runtime_status():
    from fastapi import HTTPException
    from voice_api.api.v1.endpoints.remote_execution import _runtime_modem_status
    from voice_api.schemas.execution import EndpointStatus

    assert EndpointStatus.model_validate({"alive": False}).voice_registration_known is None
    with pytest.raises(HTTPException) as exc:
        _runtime_modem_status({"alive": True, "unsupported_new_field": True})
    assert exc.value.status_code == 502
    assert "incompatible" in exc.value.detail
