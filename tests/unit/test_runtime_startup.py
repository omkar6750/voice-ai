"""Startup failures must identify configuration fields without exposing values."""

import json
from types import SimpleNamespace

import pytest
from voice_runner import main
from voice_runner.settings import DeploymentConfigurationError, RuntimeSettings

from voice_shared import logging as diagnostics


@pytest.mark.parametrize(
    "updates,component,category",
    [
        ({"runtime_control_token": ""}, "VOICE_RUNTIME_CONTROL_TOKEN", "required"),
        ({"runtime_service_token": ""}, "VOICE_RUNTIME_SERVICE_TOKEN", "required"),
        ({"api_base_url": "http://private-secret"}, "VOICE_API_BASE_URL", "https_required"),
        (
            {"runtime_public_base_url": "http://private-secret"},
            "VOICE_RUNTIME_PUBLIC_BASE_URL",
            "https_required",
        ),
    ],
)
async def test_startup_reports_setting_without_secrets(
    monkeypatch, tmp_path, updates, component, category
):
    settings = RuntimeSettings(
        _env_file=None,
        env="production",
        runtime_control_token="control-secret-canary",
        runtime_service_token="service-secret-canary",
        api_base_url="https://api.example.com",
        runtime_public_base_url="https://runtime.example.com",
        runtime_spool_dir=str(tmp_path / "spool"),
    ).model_copy(update=updates)
    # model_copy does not convert strings to SecretStr.
    from pydantic import SecretStr

    for key in ("runtime_control_token", "runtime_service_token"):
        value = getattr(settings, key)
        if isinstance(value, str):
            setattr(settings, key, SecretStr(value))
    events = []
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "configure", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        diagnostics, "emit", lambda event, **kwargs: events.append(diagnostics.redact(event))
    )
    with pytest.raises(DeploymentConfigurationError):
        async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
            pytest.fail("Invalid settings must not start the manager")
    event = next(event for event in events if event["event"] == "startup_failed")
    assert event["component"] == component
    assert event["category"] == category
    assert event["diagnostic_id"]
    output = json.dumps(events)
    assert "control-secret-canary" not in output
    assert "service-secret-canary" not in output
    assert "private-secret" not in output
