import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from twilio.base.exceptions import TwilioRestException
from voice_api.services import twilio_dispatch_service as dispatch

CALL_SID = "CA" + "a" * 32
OTHER_SID = "CA" + "b" * 32


class FakeSession:
    def __init__(self, call=None, run=None):
        self.call = call
        self.run = run
        self.commits = 0
        self.lookups = []

    async def get(self, model, identity, **kwargs):
        self.lookups.append((model.__name__, identity, kwargs))
        if model.__name__ == "Call":
            return self.call if identity == self.call.id else None
        if model.__name__ == "Run":
            return self.run if identity == self.run.id else None
        return None

    async def commit(self):
        self.commits += 1


def make_rows(*, status="queued", run_status="queued", metadata=None, sid=None):
    call = SimpleNamespace(
        id="call-1",
        run_id="run-1",
        provider="twilio",
        status=status,
        provider_call_id=sid,
        provider_metadata=dict(metadata or {}),
        target_snapshot="+15551234567",
        from_number="+14155551212",
        correlation_id="corr-1",
        telephony_connection_id="connection-1",
        ended_at=None,
    )
    run = SimpleNamespace(id="run-1", status=run_status, ended_at=None)
    return call, run


def settings(**overrides):
    values = {"public_base_url": "https://voice.example.test", "operator_token": "operator-token"}
    values.update(overrides)
    return SimpleNamespace(**values)


def install_fakes(monkeypatch, dial):
    async def resolve(_session, _connection_id):
        return None, SimpleNamespace(account_sid="AC" + "c" * 32, auth_token="secret")

    class FakeController:
        def __init__(self, credentials):
            assert credentials.auth_token == "secret"

        async def dial(self, **kwargs):
            return await dial(**kwargs)

    monkeypatch.setattr(dispatch, "resolve_twilio_credentials", resolve)
    monkeypatch.setattr(dispatch, "TwilioCallController", FakeController)


@pytest.mark.asyncio
async def test_duplicate_dispatch_is_fenced_before_second_create(monkeypatch):
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = 0

    async def dial(**_kwargs):
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.wait_for(finish.wait(), 2)
        return CALL_SID

    install_fakes(monkeypatch, dial)
    call, run = make_rows()
    session = FakeSession(call, run)
    first = asyncio.create_task(dispatch.dispatch_twilio_call(session, call, run, settings()))
    await asyncio.wait_for(entered.wait(), 1)

    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(session, call, run, settings())
    assert error.value.status_code == 409
    finish.set()
    await first
    assert calls == 1
    assert call.provider_metadata["twilio_dispatch_attempts"] == 1


@pytest.mark.asyncio
async def test_callback_binding_before_create_return_keeps_advanced_state(monkeypatch):
    call, run = make_rows()

    async def dial(**_kwargs):
        call.provider_call_id = CALL_SID
        call.status = "active"
        call.provider_metadata["twilio_status"] = "in-progress"
        run.status = "running"
        return CALL_SID

    install_fakes(monkeypatch, dial)
    result_call, result_run = await dispatch.dispatch_twilio_call(
        FakeSession(call, run), call, run, settings()
    )
    assert result_call.provider_call_id == CALL_SID
    assert result_call.status == "active"
    assert result_run.status == "running"
    assert result_call.provider_metadata["twilio_dispatch_state"] == "callback_confirmed"


@pytest.mark.asyncio
async def test_callback_sid_conflict_is_generic_and_preserves_known_identity(monkeypatch):
    call, run = make_rows()

    async def dial(**_kwargs):
        call.provider_call_id = OTHER_SID
        call.status = "active"
        run.status = "running"
        return CALL_SID

    install_fakes(monkeypatch, dial)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    assert error.value.status_code == 502
    assert error.value.detail == "Twilio call dispatch outcome is uncertain"
    assert call.provider_call_id == OTHER_SID
    assert call.status == "active" and run.status == "running"


@pytest.mark.asyncio
async def test_definite_provider_rejection_fails_only_unclaimed_queued_rows(monkeypatch):
    call, run = make_rows()

    async def dial(**_kwargs):
        raise TwilioRestException(400, "https://api.twilio.com/calls", "POST", "secret response")

    install_fakes(monkeypatch, dial)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    assert error.value.status_code == 502
    assert error.value.detail == "Twilio rejected the call request"
    assert call.status == "failed" and run.status == "failed"
    assert call.provider_metadata["twilio_dispatch_state"] == "rejected"
    assert "secret response" not in str(call.provider_metadata)


@pytest.mark.asyncio
async def test_definite_rejection_after_callback_preserves_call_and_run(monkeypatch):
    call, run = make_rows()

    async def dial(**_kwargs):
        call.provider_call_id = CALL_SID
        call.status = "active"
        call.provider_metadata["twilio_status"] = "in-progress"
        run.status = "running"
        raise TwilioRestException(400, "https://api.twilio.com/calls", "POST", "rejected")

    install_fakes(monkeypatch, dial)
    with pytest.raises(HTTPException) as caught:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    assert caught.value.detail == "Twilio call dispatch outcome is uncertain"
    assert call.provider_call_id == CALL_SID
    assert call.status == "active" and run.status == "running"
    assert call.ended_at is None and run.ended_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError("late response"), OSError("network error")])
async def test_timeout_and_network_failure_mark_uncertain_without_terminal_times(
    monkeypatch, failure
):
    call, run = make_rows()

    async def dial(**_kwargs):
        raise failure

    install_fakes(monkeypatch, dial)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    assert error.value.status_code == 502
    assert error.value.detail == "Twilio call dispatch outcome is uncertain"
    assert call.status == "dialing" and run.status == "queued"
    assert call.ended_at is None and run.ended_at is None
    assert call.provider_metadata["twilio_dispatch_attempts"] == 1


@pytest.mark.asyncio
async def test_cancelled_create_is_recorded_uncertain_and_propagates(monkeypatch):
    call, run = make_rows()
    entered = asyncio.Event()

    async def dial(**_kwargs):
        entered.set()
        await asyncio.wait_for(asyncio.Event().wait(), 2)

    install_fakes(monkeypatch, dial)
    task = asyncio.create_task(
        dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    )
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert call.status == "dialing" and run.status == "queued"
    assert call.ended_at is None and run.ended_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configuration",
    [settings(operator_token=None), settings(public_base_url="http://voice.example.test")],
)
async def test_invalid_public_url_or_missing_operator_token_prevents_credential_resolution(
    monkeypatch, configuration
):
    call, run = make_rows()

    async def unexpected(*_args, **_kwargs):
        pytest.fail("credential resolution or provider dispatch must not run")

    monkeypatch.setattr(dispatch, "resolve_twilio_credentials", unexpected)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, configuration)
    assert error.value.status_code == 422
    assert call.status == "queued"


@pytest.mark.asyncio
async def test_controller_construction_failure_keeps_queued_rows_and_attempt_eligible(monkeypatch):
    call, run = make_rows()

    async def resolve(_session, _connection_id):
        return None, SimpleNamespace(account_sid="AC" + "c" * 32, auth_token="secret")

    class BrokenController:
        def __init__(self, _credentials):
            raise OSError("private local setup details")

    monkeypatch.setattr(dispatch, "resolve_twilio_credentials", resolve)
    monkeypatch.setattr(dispatch, "TwilioCallController", BrokenController)
    session = FakeSession(call, run)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(session, call, run, settings())
    assert error.value.status_code == 503
    assert error.value.detail == "Twilio dispatch setup is unavailable"
    assert call.status == "queued" and run.status == "queued"
    assert "twilio_dispatch_attempted" not in call.provider_metadata
    assert session.commits == 0


@pytest.mark.asyncio
async def test_malformed_create_sid_is_uncertain_and_never_bound(monkeypatch):
    call, run = make_rows()

    async def dial(**_kwargs):
        return "CA12345"

    install_fakes(monkeypatch, dial)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    assert error.value.status_code == 502
    assert error.value.detail == "Twilio call dispatch outcome is uncertain"
    assert call.provider_call_id is None
    assert call.status == "dialing" and run.status == "queued"
    assert call.provider_metadata["twilio_dispatch_state"] == "uncertain"


@pytest.mark.asyncio
async def test_previous_attempt_metadata_blocks_redial(monkeypatch):
    call, run = make_rows(metadata={"twilio_dispatch_attempted": True})

    async def unexpected(**_kwargs):
        pytest.fail("a prior attempt must never be redialed")

    install_fakes(monkeypatch, unexpected)
    with pytest.raises(HTTPException) as error:
        await dispatch.dispatch_twilio_call(FakeSession(call, run), call, run, settings())
    assert error.value.status_code == 409
    assert call.status == "queued"
