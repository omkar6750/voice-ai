from itertools import product
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from voice_runtime.contracts.agent import FlowFunctionConfig
from voice_runtime.contracts.cadence import (
    LEAD_CLASSIFIER_PROMPT,
    LEAD_OUTPUT_FIELDS,
    ClassifierConfig,
    lead_classifier_contract,
)
from voice_runtime.contracts.tools import ToolConfig
from voice_runtime.execution.classifier import normalize_classifier_result
from voice_runtime.execution.native_host import NativePipelineHost
from voice_runtime.execution.pipecat_flow import compile_pipecat_flow
from voice_shared.compiler import compile_flow_json


def test_fixed_configuration_overrides_old_custom_prompts_and_questions():
    cfg = ClassifierConfig.model_validate(
        {
            "llm": {
                "provider": "sarvam",
                "model": "sarvam-105b",
                "prompt": "override",
                "output_fields": {"other": ["yes"]},
                "max_output_tokens": 1,
            }
        }
    )
    assert cfg.llm.provider == "sarvam"
    assert cfg.llm.model == "sarvam-105b"
    assert cfg.llm.prompt == LEAD_CLASSIFIER_PROMPT
    assert cfg.llm.output_fields == LEAD_OUTPUT_FIELDS
    jev = ClassifierConfig.model_validate(
        {
            "classifier_type": "jev",
            "jev": {
                "questions": {"other": {"criteria": {"yes": "test"}}},
                "output_fields": ["other"],
                "api_url": "https://unexpected.invalid",
            },
        }
    ).jev
    assert set(jev.questions) == set(LEAD_OUTPUT_FIELDS)
    assert jev.output_fields == list(LEAD_OUTPUT_FIELDS)
    assert jev.api_url == "https://api.typesafe.ai/v1/systemone"


def test_reserved_tool_cannot_accept_custom_parameters_or_http_implementation():
    tool = ToolConfig(
        name="classify_lead",
        handler="classify_lead",
        parameters={"properties": {"custom": {"type": "string"}}},
    )
    assert tool.parameters == {"type": "object", "properties": {}, "additionalProperties": False}
    with pytest.raises(ValidationError):
        ToolConfig(name="classify_lead", kind="http", http={"url": "https://example.org"})
    with pytest.raises(ValidationError):
        ToolConfig(name="other_classifier", handler="classify_lead")


def test_fixed_routes_reject_unknown_fields_and_labels():
    for branch in (
        {"field": "custom", "cases": {"yes": "next"}},
        {"field": "tone", "cases": {"angry": "next"}},
    ):
        with pytest.raises(ValidationError):
            FlowFunctionConfig(name="classify_lead", transition_to=branch)


def test_incomplete_or_forged_classifier_results_fail_closed():
    assert normalize_classifier_result({"lead_temperature": "hot"})["status"] == "error"
    assert (
        normalize_classifier_result(
            {"lead_temperature": "invented", "service_fit": "strong_fit", "tone": "receptive"},
            {"lead_temperature": ["invented"]},
        )["status"]
        == "error"
    )


@pytest.mark.asyncio
async def test_all_27_combinations_route_using_the_actual_compiled_flow():
    keys = lead_classifier_contract()["fields"]["classification_key"]
    assert len(set(keys)) == 27
    cfg = {
        "flow": {
            "initial_node": "discovery",
            "nodes": [
                {
                    "id": "discovery",
                    "role_message": "Discover",
                    "functions": [
                        {
                            "name": "classify_lead",
                            "transition_to": {
                                "field": "classification_key",
                                "cases": {key: f"target_{index}" for index, key in enumerate(keys)},
                            },
                        }
                    ],
                },
                *[{"id": f"target_{index}", "role_message": "Next"} for index in range(27)],
            ],
        },
        "classifier": {},
    }
    current = {}

    async def handler(params, manager):
        return normalize_classifier_result(current)

    host = SimpleNamespace(_snapshot=cfg, _handler=lambda name: handler, tracker=Mock())
    compiled = compile_flow_json(cfg)
    flow = compile_pipecat_flow(
        {**cfg, "_compiled_flow": compiled},
        handlers={"classify_lead": NativePipelineHost._pipecat_tool_proxy(host, "classify_lead")},
    )
    fn = flow.node("discovery")["functions"][0]
    for index, labels in enumerate(product(*LEAD_OUTPUT_FIELDS.values())):
        current = dict(zip(LEAD_OUTPUT_FIELDS, labels, strict=True))
        result, destination = await fn.handler({}, SimpleNamespace(current_node="discovery"))
        assert result["classification_key"] == keys[index]
        assert destination == flow.node(f"target_{index}")


def test_empty_case_mapping_compiles_as_stay_or_default():
    for default in (None, "next"):
        cfg = {
            "flow": {
                "initial_node": "start",
                "nodes": [
                    {
                        "id": "start",
                        "functions": [
                            {
                                "name": "classify_lead",
                                "transition_to": {"field": "tone", "cases": {}, "default": default},
                            }
                        ],
                    },
                    {"id": "next"},
                ],
            }
        }
        compiled = compile_flow_json(cfg)
        assert compiled["nodes"]["start"]["functions"][0]["transition_to"] == default

        async def handler(flow_manager, **params):
            from pipecat.flows import TRANSITION_IN_YAML

            return {}, TRANSITION_IN_YAML

        compile_pipecat_flow(
            {**cfg, "_compiled_flow": compiled}, handlers={"classify_lead": handler}
        )


def test_dashboard_enum_fixture_matches_server_contract():
    import json
    from pathlib import Path

    fixture = (
        Path(__file__).resolve().parents[2]
        / "apps/dashboard/scripts/lead-classifier-contract.fixture.json"
    )
    assert json.loads(fixture.read_text(encoding="utf-8")) == lead_classifier_contract()


@pytest.mark.asyncio
async def test_custom_combination_routing_waits_for_result_without_legacy_policy(monkeypatch):
    from voice_runtime.execution import tool_dispatch

    async def classify(**kwargs):
        return {"lead_temperature": "hot", "service_fit": "strong_fit", "tone": "receptive"}

    monkeypatch.setattr(tool_dispatch, "run_selected_classifier", classify)
    monkeypatch.setattr(
        tool_dispatch, "_extract_transcript", lambda *args: "Caller wants a project"
    )
    host = SimpleNamespace(
        _snapshot={
            "classifier": {},
            "flow": {
                "nodes": [
                    {
                        "id": "discovery",
                        "functions": [
                            {
                                "name": "classify_lead",
                                "transition_to": {
                                    "field": "classification_key",
                                    "cases": {"hot|strong_fit|receptive": "next"},
                                },
                            }
                        ],
                    }
                ]
            },
        },
        settings=SimpleNamespace(),
        tracker=Mock(),
        _is_nonblocking_tool=tool_dispatch.NativeToolDispatch._is_nonblocking_tool,
    )
    result = await tool_dispatch.NativeToolDispatch._handler(host, "classify_lead")(
        {}, SimpleNamespace(current_node="discovery")
    )
    assert result["classification_key"] == "hot|strong_fit|receptive"
    assert result.get("status") != "pending"


@pytest.mark.asyncio
async def test_custom_classifier_route_fences_late_results():
    from pipecat.flows import NO_RESPONSE

    manager = SimpleNamespace(current_node="discovery")

    async def handler(params, flow_manager):
        flow_manager.current_node = "closing"
        return normalize_classifier_result(
            {"lead_temperature": "hot", "service_fit": "strong_fit", "tone": "receptive"}
        )

    host = SimpleNamespace(
        _snapshot={"classifier": {}}, _handler=lambda name: handler, tracker=Mock()
    )
    _, destination = await NativePipelineHost._pipecat_tool_proxy(host, "classify_lead")(manager)
    assert destination is NO_RESPONSE
