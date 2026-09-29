import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from voice_api.core.config import Settings
from voice_api.core.hosting import require_hosted_call_admission, require_local_modem


def test_hosted_calls_fail_closed_until_capacity_accepted():
    settings = Settings(_env_file=None, env="production")
    with pytest.raises(HTTPException) as error:
        require_hosted_call_admission("browser", settings)
    assert error.value.status_code == 503


def test_hosted_profile_never_admits_modem():
    settings = Settings(_env_file=None, env="production", hosted_calls_enabled=True)
    for provider in ("browser", "twilio"):
        require_hosted_call_admission(provider, settings)
    with pytest.raises(HTTPException) as error:
        require_hosted_call_admission("sim7600", settings)
    assert error.value.status_code == 409


def test_local_modem_inventory_is_unavailable_in_production(monkeypatch):
    monkeypatch.setattr(
        "voice_api.core.hosting.get_settings", lambda: Settings(_env_file=None, env="production")
    )
    with pytest.raises(HTTPException) as error:
        require_local_modem()
    assert error.value.status_code == 404


@pytest.mark.parametrize(
    "setting", [{"max_concurrent_calls": 2}, {"call_max_duration_seconds": 301}]
)
def test_free_demo_limits_cannot_be_relaxed_accidentally(setting):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **setting)
