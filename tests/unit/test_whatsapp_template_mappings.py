import pytest
from fastapi import HTTPException
from voice_api.api.v1.endpoints.integrations import _validate_template_parameter_mappings


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
