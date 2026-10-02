import pytest
from pydantic import ValidationError
from voice_runtime.contracts import RetrievalConfig, ToolConfig


def whatsapp_config() -> dict:
    return {
        "connection_id": "connection-1",
        "template_name": "dialtone_followup",
        "language": "en",
        "header": {"format": "IMAGE", "media_id": "74506"},
        "parameter_mappings": {"1": "caller_name", "2": "param_2"},
    }


def test_whatsapp_template_tool_uses_meta_media_reference() -> None:
    config = ToolConfig.model_validate(
        {
            "name": "whatsapp_template_dialtone_followup",
            "description": "Send the approved follow-up template.",
            "kind": "registered",
            "handler": "send_whatsapp_template",
            "whatsapp": whatsapp_config(),
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_name": {"type": "string"},
                    "param_2": {"type": "string"},
                },
            },
        }
    )

    assert config.whatsapp is not None
    assert config.whatsapp.header is not None
    assert config.whatsapp.header.format == "IMAGE"
    assert config.whatsapp.header.media_id == "74506"
    assert config.whatsapp.parameter_mappings["2"] == "param_2"


def test_template_handler_requires_account_scoped_configuration() -> None:
    with pytest.raises(ValidationError, match="requires WhatsApp settings"):
        ToolConfig.model_validate(
            {
                "name": "whatsapp_template_dialtone_followup",
                "kind": "registered",
                "handler": "send_whatsapp_template",
            }
        )


def test_direct_whatsapp_tools_require_an_explicit_connection_pin() -> None:
    with pytest.raises(ValidationError, match="pinned whatsapp_connection_id"):
        ToolConfig.model_validate(
            {"name": "send_whatsapp_message", "handler": "send_whatsapp_message"}
        )
    config = ToolConfig.model_validate(
        {
            "name": "send_whatsapp_message",
            "handler": "send_whatsapp_message",
            "whatsapp_connection_id": "connection-1",
        }
    )
    assert config.whatsapp_connection_id == "connection-1"


def test_http_tool_cannot_carry_whatsapp_settings() -> None:
    with pytest.raises(ValidationError, match="HTTP tools cannot contain WhatsApp"):
        ToolConfig.model_validate(
            {
                "name": "http_tool",
                "kind": "http",
                "http": {"url": "https://example.com", "method": "POST"},
                "whatsapp": whatsapp_config(),
            }
        )


def test_removed_wait_fields_are_rejected_by_strict_contracts() -> None:
    with pytest.raises(ValidationError, match="wait"):
        ToolConfig.model_validate(
            {
                "name": "send_message",
                "kind": "registered",
                "handler": "send_whatsapp_message",
                "whatsapp_connection_id": "connection-1",
                "wait": {"mode": "acknowledge_then_wait", "acknowledgement": "Please wait"},
            }
        )
    with pytest.raises(ValidationError, match="wait"):
        RetrievalConfig.model_validate({"wait": {"mode": "silent_wait"}})
