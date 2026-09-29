from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from twilio.request_validator import RequestValidator
from voice_api.api.deps import get_session
from voice_api.api.v1.endpoints.calls import start_call
from voice_api.main import app
from voice_api.models import Call, Contact, IntegrationConnection, Run
from voice_api.models.common import new_id
from voice_api.schemas.call import StartCallBody, TelephonySelection
from voice_api.services.call_service import (
    apply_twilio_call_status,
    apply_twilio_stream_status,
    queue_call,
)
from voice_runtime.call_capture import CallCapture
from voice_runtime.telephony.twilio import TwilioCredentials


@pytest.mark.asyncio
async def test_queue_call_twilio():
    session = AsyncMock(spec=AsyncSession)
    contact_id = new_id()
    version_id = new_id()
    conn_id = new_id()

    contact = Contact(
        id=contact_id,
        name="Test Contact",
        phone_number="+919876543210",
        timezone="Asia/Kolkata",
    )
    from voice_api.models import AgentVersion

    version = AgentVersion(
        id=version_id,
        agent_id=new_id(),
        version=1,
        revision=1,
        status="published",
        config={"flow": {"nodes": []}},
    )
    conn = IntegrationConnection(
        id=conn_id,
        label="Primary Twilio",
        provider="twilio_voice",
        enabled=True,
        config={
            "account_sid": "AC12345678901234567890123456789012",
            "account_type": "Full",
            "phone_numbers": [
                {"sid": "PN1", "phone_number": "+14155551212", "voice": True},
            ],
        },
    )

    async def mock_get(model, pk):
        if model is Contact and pk == contact_id:
            return contact
        if model is AgentVersion and pk == version_id:
            return version
        if model is IntegrationConnection and pk == conn_id:
            return conn
        return None

    session.get.side_effect = mock_get

    with patch("voice_api.services.call_service.resolve") as mock_resolve:
        mock_resolve.return_value = ({"flow": {}}, "hash123")
        telephony = TelephonySelection(
            provider="twilio",
            connection_id=conn_id,
            from_number="+14155551212",
        )
        run, call = await queue_call(
            session,
            contact_id=contact_id,
            agent_version_id=version_id,
            telephony=telephony,
        )

        assert run.endpoint_id is None
        assert call.provider == "twilio"
        assert call.telephony_connection_id == conn_id
        assert call.from_number == "+14155551212"
        assert call.status == "queued"
        assert call.provider_metadata["phone_number_sid"] == "PN1"


@pytest.mark.asyncio
async def test_queue_call_twilio_trial_rejected():
    session = AsyncMock(spec=AsyncSession)
    contact_id = new_id()
    version_id = new_id()
    conn_id = new_id()

    contact = Contact(id=contact_id, name="Test", phone_number="+919876543210")
    from voice_api.models import AgentVersion

    version = AgentVersion(id=version_id, agent_id=new_id(), status="published")
    conn = IntegrationConnection(
        id=conn_id,
        provider="twilio_voice",
        enabled=True,
        config={"account_type": "Trial", "phone_numbers": []},
    )

    async def mock_get(model, pk):
        if model is Contact:
            return contact
        if model is AgentVersion:
            return version
        if model is IntegrationConnection:
            return conn
        return None

    session.get.side_effect = mock_get

    with pytest.raises(HTTPException) as exc:
        await queue_call(
            session,
            contact_id=contact_id,
            agent_version_id=version_id,
            telephony=TelephonySelection(
                provider="twilio",
                connection_id=conn_id,
                from_number="+14155551212",
            ),
        )
    assert exc.value.status_code == 422
    assert "trial accounts cannot place Media Stream calls" in exc.value.detail


@pytest.mark.asyncio
async def test_apply_twilio_call_status():
    session = AsyncMock(spec=AsyncSession)
    run = Run(id=new_id(), status="running")
    call = Call(id=new_id(), run_id=run.id, provider="twilio", status="dialing")

    async def mock_get(model, pk, **kwargs):
        if model is Call and pk == call.id:
            return call
        if model is Run and pk == run.id:
            return run
        return None

    session.get.side_effect = mock_get

    # answered -> in-progress / active
    await apply_twilio_call_status(session, call, "in-progress")
    assert call.status == "active"
    assert call.answered_at is not None

    # Provider call completion is not proof of successful business execution.
    await apply_twilio_call_status(session, call, "completed")
    assert call.status == "completed"
    assert call.ended_at is not None
    assert run.status == "running"


@pytest.mark.asyncio
async def test_apply_twilio_stream_status():
    session = AsyncMock(spec=AsyncSession)
    call = Call(id=new_id(), provider="twilio", provider_metadata={})
    session.get.return_value = call

    await apply_twilio_stream_status(
        session, call, stream_sid="MZ123", event="stream-started", error=None
    )
    assert call.provider_metadata["stream_sid"] == "MZ123"
    assert call.provider_metadata["stream_status"] == "started"

    await apply_twilio_stream_status(
        session, call, stream_sid="MZ123", event="stream-error", error="WebSocket error 1006"
    )
    assert call.provider_metadata["stream_status"] == "error"
    assert call.provider_metadata["stream_error"] == "Twilio reported a stream error"


@pytest.mark.asyncio
async def test_call_status_endpoint(monkeypatch):
    import httpx
    from voice_api.api.deps import get_session
    from voice_api.main import app
    from voice_runtime.telephony.twilio import TwilioCredentials

    session_mock = AsyncMock(spec=AsyncSession)
    corr_id = new_id()
    call = Call(
        id=new_id(),
        provider="twilio",
        correlation_id=corr_id,
        telephony_connection_id="conn-1",
        provider_call_id="CA12345",
        status="dialing",
        provider_metadata={},
    )
    session_mock.get.return_value = call

    async def mock_get_session():
        yield session_mock

    app.dependency_overrides[get_session] = mock_get_session

    try:
        with (
            patch(
                "voice_api.api.v1.endpoints.telephony.get_by_correlation_id",
                return_value=call,
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.resolve_twilio_credentials",
                return_value=(
                    None,
                    TwilioCredentials(account_sid="AC123", auth_token="token"),
                ),
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.get_settings",
                return_value=SimpleNamespace(public_base_url=None),
            ),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/telephony/twilio/call-status/{corr_id}",
                    data={"CallSid": "CA12345", "CallStatus": "in-progress"},
                )
                assert res.status_code == 204
                assert call.status == "active"
                assert call.provider_metadata["twilio_status"] == "in-progress"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_stream_status_endpoint(monkeypatch):
    session_mock = AsyncMock()
    corr_id = new_id()
    call = Call(
        id=new_id(),
        provider="twilio",
        correlation_id=corr_id,
        telephony_connection_id="conn-1",
        provider_call_id="CA12345",
        status="active",
        provider_metadata={},
    )
    session_mock.get.return_value = call

    async def mock_get_session():
        yield session_mock

    app.dependency_overrides[get_session] = mock_get_session

    try:
        with (
            patch(
                "voice_api.api.v1.endpoints.telephony.get_by_correlation_id",
                return_value=call,
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.resolve_twilio_credentials",
                return_value=(
                    None,
                    TwilioCredentials(account_sid="AC123", auth_token="token"),
                ),
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.get_settings",
                return_value=SimpleNamespace(public_base_url=None),
            ),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    f"/api/v1/telephony/twilio/stream-status/{corr_id}",
                    data={
                        "StreamSid": "MZ999",
                        "StatusCallbackEvent": "stream-started",
                    },
                )
                assert res.status_code == 204
                assert call.provider_metadata["stream_sid"] == "MZ999"
                assert call.provider_metadata["stream_status"] == "started"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_signature_required_when_public_base_url_set():
    corr_id = "corr-sig-test"
    session_mock = AsyncMock(spec=AsyncSession)
    call = Call(
        id="c1",
        run_id="r1",
        correlation_id=corr_id,
        contact_id="cnt1",
        agent_version_id="av1",
        provider="twilio",
        telephony_connection_id="conn1",
        status="active",
        provider_metadata={},
    )
    session_mock.get.return_value = call

    async def mock_get_session():
        yield session_mock

    app.dependency_overrides[get_session] = mock_get_session

    try:
        with (
            patch(
                "voice_api.api.v1.endpoints.telephony.get_by_correlation_id",
                return_value=call,
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.resolve_twilio_credentials",
                return_value=(
                    None,
                    TwilioCredentials(account_sid="AC123", auth_token="token"),
                ),
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.get_settings",
                return_value=SimpleNamespace(public_base_url="https://voice.example.com"),
            ),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # Request without signature must be rejected with 403
                res = await client.post(
                    f"/api/v1/telephony/twilio/call-status/{corr_id}",
                    data={"CallStatus": "in-progress"},
                )
                assert res.status_code == 403
                assert "signature" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_signature_accepted_when_valid():
    corr_id = "corr-sig-valid"
    session_mock = AsyncMock(spec=AsyncSession)
    call = Call(
        id="c1",
        run_id="r1",
        correlation_id=corr_id,
        contact_id="cnt1",
        agent_version_id="av1",
        provider="twilio",
        telephony_connection_id="conn1",
        status="active",
        provider_metadata={},
    )
    session_mock.get.return_value = call

    async def mock_get_session():
        yield session_mock

    app.dependency_overrides[get_session] = mock_get_session

    auth_token = "secret_auth_token_999"
    validator = RequestValidator(auth_token)
    url = f"https://voice.example.com/api/v1/telephony/twilio/call-status/{corr_id}"
    data = {"CallSid": "CA12345", "CallStatus": "in-progress"}
    sig = validator.compute_signature(url, data)

    try:
        with (
            patch(
                "voice_api.api.v1.endpoints.telephony.get_by_correlation_id",
                return_value=call,
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.resolve_twilio_credentials",
                return_value=(
                    None,
                    TwilioCredentials(account_sid="AC123", auth_token=auth_token),
                ),
            ),
            patch(
                "voice_api.api.v1.endpoints.telephony.get_settings",
                return_value=SimpleNamespace(public_base_url="https://voice.example.com"),
            ),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="https://voice.example.com"
            ) as client:
                res = await client.post(
                    f"/api/v1/telephony/twilio/call-status/{corr_id}",
                    data=data,
                    headers={"X-Twilio-Signature": sig},
                )
                assert res.status_code == 204
                assert call.status == "active"
                assert call.provider_metadata["twilio_status"] == "in-progress"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_exception_sanitization_on_dial_failure():
    conn_id = "conn-dial-err"
    conn = IntegrationConnection(
        id=conn_id,
        label="Primary Twilio",
        provider="twilio_voice",
        enabled=True,
        config={
            "account_sid": "AC12345678901234567890123456789012",
            "account_type": "Full",
            "phone_numbers": [{"sid": "PN1", "phone_number": "+14155551212", "voice": True}],
        },
    )

    class FakeTwilioException(Exception):
        msg = "Twilio rejected request: secret auth_token_secret_12345 should not leak"

    async def mock_dial(*args, **kwargs):
        raise FakeTwilioException(
            "Twilio rejected request: secret auth_token_secret_12345 should not leak"
        )

    session_mock = AsyncMock(spec=AsyncSession)
    run_mock = Run(
        id="run-err",
        status="queued",
        agent_version_id="av1",
        contact_id="cnt1",
        config_hash="h1",
        snapshot_schema_version=1,
    )
    call_mock = Call(
        id="call-err",
        run_id="run-err",
        correlation_id="corr-err",
        contact_id="cnt1",
        agent_version_id="av1",
        provider="twilio",
        telephony_connection_id=conn_id,
        target_snapshot="+15551234567",
        from_number="+14155551212",
        status="queued",
        provider_metadata={},
    )

    with (
        patch("voice_api.api.v1.endpoints.calls.queue_call", return_value=(run_mock, call_mock)),
        patch(
            "voice_api.api.v1.endpoints.calls.get_settings",
            return_value=SimpleNamespace(public_base_url="https://test.com", operator_token="tok"),
        ),
        patch(
            "voice_api.services.twilio_service.resolve_twilio_credentials",
            return_value=(
                conn,
                TwilioCredentials(account_sid="AC123", auth_token="auth_token_secret_12345"),
            ),
        ),
        patch("voice_runtime.telephony.twilio.TwilioCallController.dial", side_effect=mock_dial),
    ):
        body = StartCallBody(
            contact_id="cnt1",
            agent_version_id="av1",
            telephony=TelephonySelection(
                provider="twilio", connection_id=conn_id, from_number="+14155551212"
            ),
            dispatch=True,
        )
        with pytest.raises(HTTPException) as exc_info:
            await start_call(body, session=session_mock, _=None)

        assert exc_info.value.status_code == 502
        assert "auth_token_secret_12345" not in exc_info.value.detail
        assert "[REDACTED]" in exc_info.value.detail
        assert "auth_token_secret_12345" not in call_mock.provider_metadata["error"]
        assert "[REDACTED]" in call_mock.provider_metadata["error"]


def test_call_capture_creates_wav_files_on_close(tmp_path):
    capture = CallCapture(tmp_path, sample_rate=8000)
    capture.close()
    assert (tmp_path / "input.wav").is_file()
    assert (tmp_path / "output.wav").is_file()
    assert (tmp_path / "mixed.wav").is_file()
