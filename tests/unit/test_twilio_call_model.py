"""Unit tests for Twilio database models and constraints."""

from voice_api.models import Call, Run
from voice_api.models.common import new_id


def test_call_model_telephony_fields():
    call_id = new_id()
    run_id = new_id()
    contact_id = new_id()
    version_id = new_id()

    # SIM7600 call without telephony_connection_id
    sim_call = Call(
        id=call_id,
        run_id=run_id,
        contact_id=contact_id,
        agent_version_id=version_id,
        provider="sim7600",
        target_snapshot="+15551234567",
    )
    assert sim_call.provider == "sim7600"
    assert sim_call.telephony_connection_id is None
    assert sim_call.from_number is None

    # Twilio call with telephony_connection_id and from_number
    twilio_call = Call(
        id=new_id(),
        run_id=new_id(),
        contact_id=contact_id,
        agent_version_id=version_id,
        provider="twilio",
        telephony_connection_id="conn_twilio_123",
        from_number="+14155551212",
        correlation_id=new_id(),
        target_snapshot="+919876543210",
        provider_metadata={
            "stream_sid": "MZ12345",
            "phone_number_sid": "PN12345",
            "from_number": "+14155551212",
            "twilio_status": "in-progress",
            "stream_status": "started",
        },
    )
    assert twilio_call.provider == "twilio"
    assert twilio_call.telephony_connection_id == "conn_twilio_123"
    assert twilio_call.from_number == "+14155551212"
    assert twilio_call.provider_metadata["stream_sid"] == "MZ12345"
    assert twilio_call.provider_metadata["phone_number_sid"] == "PN12345"


def test_twilio_run_endpoint_id_none():
    # Twilio runs must have endpoint_id = None
    run = Run(
        id=new_id(),
        agent_version_id=new_id(),
        endpoint_id=None,
        channel="phone",
        status="queued",
        resolved_config={},
    )
    assert run.endpoint_id is None
    assert run.channel == "phone"
    assert run.status == "queued"
    assert hasattr(run, "claim_token")
    assert hasattr(run, "lease_expires_at")
