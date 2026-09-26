"""Unit tests for Twilio credentials, number synchronization, and TwiML builder."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from voice_api.models import IntegrationConnection, IntegrationSecret
from voice_api.models.common import new_id
from voice_api.services.twilio_service import (
    resolve_twilio_credentials,
    test_twilio_connection,
    validate_from_number,
)
from voice_runtime.telephony.twilio import (
    PublicTelephonyUrls,
    TwilioCredentials,
    build_twilio_stream_twiml,
)


def test_public_telephony_urls():
    urls = PublicTelephonyUrls("https://voice.example.com")
    assert (
        urls.twilio_call_status("corr-123")
        == "https://voice.example.com/api/v1/telephony/twilio/call-status/corr-123"
    )
    assert (
        urls.twilio_stream_status("corr-123")
        == "https://voice.example.com/api/v1/telephony/twilio/stream-status/corr-123"
    )
    assert (
        urls.twilio_media("corr-123")
        == "wss://voice.example.com/api/v1/telephony/twilio/media/corr-123"
    )

    http_urls = PublicTelephonyUrls("http://localhost:8000")
    assert (
        http_urls.twilio_media("corr-123")
        == "ws://localhost:8000/api/v1/telephony/twilio/media/corr-123"
    )


def test_build_twilio_stream_twiml():
    twiml = build_twilio_stream_twiml(
        media_ws_url="wss://voice.example.com/api/v1/telephony/twilio/media/c1",
        stream_status_callback_url="https://voice.example.com/api/v1/telephony/twilio/stream-status/c1",
        correlation_id="c1",
        run_id="r1",
    )
    assert "<Response>" in twiml
    assert "<Connect>" in twiml
    assert "<Stream" in twiml
    assert 'url="wss://voice.example.com/api/v1/telephony/twilio/media/c1"' in twiml
    assert (
        'statusCallback="https://voice.example.com/api/v1/telephony/twilio/stream-status/c1"'
        in twiml
    )
    assert '<Parameter name="correlation_id" value="c1"' in twiml
    assert '<Parameter name="run_id" value="r1"' in twiml


@pytest.mark.asyncio
async def test_resolve_twilio_credentials():
    session = AsyncMock()
    conn_id = new_id()
    conn = IntegrationConnection(
        id=conn_id,
        label="Test Twilio",
        provider="twilio_voice",
        config={"account_sid": "AC12345678901234567890123456789012"},
        enabled=True,
    )
    secret = IntegrationSecret(
        id=new_id(),
        connection_id=conn_id,
        name="auth_token",
        ciphertext="encrypted_token",
        key_id="k1",
    )
    session.get.return_value = conn
    session.scalar.return_value = secret

    with patch("voice_api.services.twilio_service.CredentialVault.from_env") as mock_vault:
        mock_vault.return_value.decrypt.return_value = "secret_auth_token"
        _, creds = await resolve_twilio_credentials(session, conn_id)
        assert creds.account_sid == "AC12345678901234567890123456789012"
        assert creds.auth_token == "secret_auth_token"


@pytest.mark.asyncio
async def test_resolve_twilio_credentials_validation():
    session = AsyncMock()
    conn_id = new_id()

    # Wrong provider
    conn = IntegrationConnection(
        id=conn_id,
        label="Test WA",
        provider="whatsapp",
        config={},
        enabled=True,
    )
    session.get.return_value = conn
    with pytest.raises(HTTPException) as exc:
        await resolve_twilio_credentials(session, conn_id)
    assert exc.value.status_code == 422
    assert "not a Twilio Voice connection" in exc.value.detail

    # Disabled
    conn.provider = "twilio_voice"
    conn.enabled = False
    with pytest.raises(HTTPException) as exc:
        await resolve_twilio_credentials(session, conn_id, require_enabled=True)
    assert exc.value.status_code == 422
    assert "disabled" in exc.value.detail


@pytest.mark.asyncio
async def test_test_twilio_connection_full_account():
    creds = TwilioCredentials(account_sid="AC12345678901234567890123456789012", auth_token="token")

    with patch("voice_api.services.twilio_service.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        account_mock = MagicMock()
        account_mock.status = "active"
        account_mock.type = "Full"
        client.api.v2010.accounts.return_value.fetch.return_value = account_mock

        num1 = MagicMock()
        num1.sid = "PN1"
        num1.phone_number = "+14155551212"
        num1.friendly_name = "US Sales"
        num1.capabilities = {"voice": True}

        num2 = MagicMock()
        num2.sid = "PN2"
        num2.phone_number = "+14155551213"
        num2.friendly_name = "SMS only"
        num2.capabilities = {"voice": False}

        client.incoming_phone_numbers.list.return_value = [num1, num2]

        res = await test_twilio_connection(creds)
        assert res["status"] == "ok"
        assert res["account_type"] == "Full"
        assert len(res["phone_numbers"]) == 1
        assert res["phone_numbers"][0]["phone_number"] == "+14155551212"
        assert res["account_sid"] == "AC...9012"


@pytest.mark.asyncio
async def test_test_twilio_connection_trial_account_warning():
    creds = TwilioCredentials(account_sid="AC12345678901234567890123456789012", auth_token="token")

    with patch("voice_api.services.twilio_service.Client") as mock_client_cls:
        client = mock_client_cls.return_value
        account_mock = MagicMock()
        account_mock.status = "active"
        account_mock.type = "Trial"
        client.api.v2010.accounts.return_value.fetch.return_value = account_mock

        res = await test_twilio_connection(creds)
        assert res["status"] == "warning"
        assert res["account_type"] == "Trial"
        assert "Trial accounts block <Stream>" in res["message"]
        assert res["phone_numbers"] == []


def test_validate_from_number():
    conn = IntegrationConnection(
        id=new_id(),
        label="Twilio",
        provider="twilio_voice",
        config={
            "phone_numbers": [
                {"sid": "PN1", "phone_number": "+14155551212", "voice": True},
                {"sid": "PN2", "phone_number": "+14155559999", "voice": False},
            ]
        },
    )

    valid = validate_from_number(conn, "+14155551212")
    assert valid["sid"] == "PN1"

    with pytest.raises(HTTPException) as exc:
        validate_from_number(conn, "+14155559999")
    assert exc.value.status_code == 422

    with pytest.raises(HTTPException) as exc:
        validate_from_number(conn, "+19999999999")
    assert exc.value.status_code == 422
