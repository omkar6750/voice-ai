from voice_api.main import app
from voice_api.schemas.workspace import WorkspaceUpdateRequest


def test_workspace_update_uses_workspace_config_contract() -> None:
    payload = {
        "revision": 1,
        "config": {
            "recording_retention_days": 7,
            "pipeline_log_retention_days": 7,
            "pipeline_logs_enabled": False,
            "automatic_callbacks_enabled": False,
            "callback_due_window_minutes": 15,
        },
    }

    request = WorkspaceUpdateRequest.model_validate(payload)

    assert request.config.recording_retention_days == 7
    openapi = app.openapi()
    operation = openapi["paths"]["/api/v1/workspace"]["patch"]
    request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    request_model = openapi["components"]["schemas"][request_schema["$ref"].rsplit("/", 1)[-1]]
    config_schema = request_model["properties"]["config"]
    assert config_schema["$ref"].endswith("/WorkspaceConfig")
