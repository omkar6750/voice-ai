from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from voice_api.api.v1.endpoints.integrations import (
    _snapshot_references_media,
    _validate_template_parameter_mappings,
    _whatsapp_config_references_media,
)
from voice_api.api.v1.endpoints.tools import _whatsapp_media_issue
from voice_api.schemas.integrations import GenerateTemplateToolBody
from voice_runtime.contracts import ToolConfig


def test_template_mapping_accepts_placeholder_indexes_and_tool_arguments() -> None:
    _validate_template_parameter_mappings(
        {"1": "caller_name", "2": "param_2"},
        {"1", "2"},
        {"caller_name", "param_2", "to"},
    )


def test_template_mapping_rejects_unknown_placeholder_index() -> None:
    with pytest.raises(HTTPException, match="unknown template placeholders"):
        _validate_template_parameter_mappings(
            {"3": "param_2"}, {"1", "2"}, {"caller_name", "param_2"}
        )


def test_template_mapping_rejects_unknown_tool_argument() -> None:
    with pytest.raises(HTTPException, match="unknown tool arguments"):
        _validate_template_parameter_mappings(
            {"2": "unknown_arg"}, {"1", "2"}, {"caller_name", "param_2"}
        )


def test_template_generation_media_field_requires_meta_provider_id() -> None:
    with pytest.raises(ValidationError):
        GenerateTemplateToolBody(template_name="followup", header_media_id="local-media-uuid")
    body = GenerateTemplateToolBody(template_name="followup", header_media_id="123456")
    assert body.header_media_id == "123456"


def test_media_reference_guards_are_scoped_to_connection_and_provider_id() -> None:
    media = SimpleNamespace(id="local-row", provider_media_id="123456")
    assert _whatsapp_config_references_media(
        {"connection_id": "connection-1", "header": {"media_id": "123456"}},
        connection_id="connection-1",
        media=media,
    )
    assert not _whatsapp_config_references_media(
        {"connection_id": "connection-2", "header": {"media_id": "123456"}},
        connection_id="connection-1",
        media=media,
    )
    assert _snapshot_references_media(
        {
            "_resolved": {
                "tools": {
                    "followup": {
                        "definition": {
                            "whatsapp": {
                                "connection_id": "connection-1",
                                "header": {"media_id": "123456"},
                            }
                        }
                    }
                }
            }
        },
        connection_id="connection-1",
        media=media,
    )


@pytest.mark.asyncio
async def test_tool_validation_requires_available_media_on_enabled_connection() -> None:
    config = ToolConfig.model_validate(
        {
            "name": "whatsapp_followup",
            "kind": "registered",
            "handler": "send_whatsapp_template",
            "whatsapp": {
                "connection_id": "connection-1",
                "template_name": "followup",
                "language": "en_US",
                "header": {"format": "IMAGE", "media_id": "123456"},
            },
        }
    )

    class FakeSession:
        connection = SimpleNamespace(provider="whatsapp", enabled=True, deleted_at=None)
        media = SimpleNamespace(media_type="image")

        async def get(self, _model, _id):
            return self.connection

        async def scalar(self, _query):
            return self.media

    assert await _whatsapp_media_issue(FakeSession(), config) is None

    FakeSession.media = None
    issue = await _whatsapp_media_issue(FakeSession(), config)
    assert issue and "unavailable" in issue

    FakeSession.connection = SimpleNamespace(provider="whatsapp", enabled=False, deleted_at=None)
    issue = await _whatsapp_media_issue(FakeSession(), config)
    assert issue and "enabled WhatsApp" in issue
