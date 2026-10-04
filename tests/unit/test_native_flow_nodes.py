from pathlib import Path
from types import SimpleNamespace

import pytest
from pipecat.flows import ContextStrategy, ContextStrategyConfig, NodeConfig
from pipecat.flows.types import TRANSITION_IN_YAML, FlowsFunctionSchema
from voice_runtime.execution.native import NativePipelineHost


def _host() -> NativePipelineHost:
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host._snapshot = {
        "flow": {
            "initial_node": "opening",
            "nodes": [
                {
                    "id": "opening",
                    "prompt": "Ask whether they have a moment.",
                    "tool_bindings": [],
                    "transitions": ["closing"],
                    "respond_immediately": True,
                    "context_strategy": "append",
                },
                {
                    "id": "closing",
                    "prompt": "Thank them and end the call.",
                    "tool_bindings": [],
                    "transitions": [],
                    "respond_immediately": True,
                    "context_strategy": "reset",
                },
            ],
        },
        "system_prompt": "Follow the system prompt.",
        "_resolved": {
            "tools": {
                "change_node": {
                    "definition": {
                        "description": "Move to an allowed node.",
                        "parameters": {
                            "type": "object",
                            "properties": {"node": {"type": "string"}},
                            "required": ["node"],
                        },
                    }
                }
            }
        },
    }
    host._nodes = {
        "opening": {
            "id": "opening",
            "prompt": "Ask whether they have a moment.",
            "tool_bindings": [],
            "transitions": ["closing"],
            "respond_immediately": True,
            "context_strategy": "append",
        },
        "closing": {
            "id": "closing",
            "prompt": "Thank them and end the call.",
            "tool_bindings": [],
            "transitions": [],
            "respond_immediately": True,
            "context_strategy": "reset",
        },
    }
    host._pipecat_flow = __import__(
        "voice_runtime.execution.pipecat_flow", fromlist=["compile_pipecat_flow"]
    ).compile_pipecat_flow(host._snapshot)
    return host


def test_saved_node_uses_pipecat_config_and_native_transition_function():
    host = _host()

    node: NodeConfig = host._node("opening")

    assert node["name"] == "opening"
    assert node["role_message"] == (
        "Follow the system prompt.\n\nCurrent node objective:\nAsk whether they have a moment."
    )
    assert node["task_messages"] == []
    assert node["context_strategy"] == ContextStrategyConfig(strategy=ContextStrategy.APPEND)
    assert len(node["functions"]) == 1
    assert isinstance(node["functions"][0], FlowsFunctionSchema)
    assert node["functions"][0].name == "go_to_closing"
    assert node["functions"][0].properties == {}
    serialized = node["functions"][0].to_function_schema().to_default_dict()
    assert serialized["parameters"]["properties"] == {}


@pytest.mark.asyncio
async def test_pipecat_transition_only_function_targets_the_runtime_enriched_node():
    host = _host()
    for node_id in host._nodes:
        host._pipecat_flow.node(node_id).update(host._node(node_id))

    edge = host._pipecat_flow.node("opening")["functions"][0]
    _result, destination = await edge.handler({}, None)

    assert destination["name"] == "closing"
    assert destination["context_strategy"].strategy == ContextStrategy.RESET


def test_node_role_message_uses_provider_system_channel_and_keeps_context_messages_separate():
    host = _host()
    host._nodes["opening"].update(
        role_message="Use a calm voice.",
        task_messages=[{"role": "assistant", "content": "Previous assistant context."}],
    )
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._snapshot["flow"]["nodes"][0].update(host._nodes["opening"])
    host._pipecat_flow = compile_pipecat_flow(host._snapshot)

    node = host._node("opening")

    assert node["role_message"] == (
        "Follow the system prompt.\n\nUse a calm voice.\n\n"
        "Current node objective:\nAsk whether they have a moment."
    )
    assert node["task_messages"] == [
        {"role": "assistant", "content": "Previous assistant context."}
    ]


def test_native_edge_functions_follow_the_node_transition_graph():
    host = _host()
    host._nodes["alternate"] = {
        **host._nodes["opening"],
        "id": "alternate",
        "transitions": ["opening", "closing"],
    }
    host._snapshot["flow"]["nodes"].append(host._nodes["alternate"])
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._pipecat_flow = compile_pipecat_flow(host._snapshot)

    opening_function = host._node("opening")["functions"][0]
    alternate_functions = host._node("alternate")["functions"]

    assert opening_function.name == "go_to_closing"
    assert {function.name for function in alternate_functions} == {
        "go_to_opening",
        "go_to_closing",
    }


def test_compiler_preserves_native_branch_table_on_tool_transition():
    host = _host()
    tool = {
        "description": "Check lead qualification.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    host._snapshot["_resolved"]["tools"]["check_lead"] = {"definition": tool}
    host._snapshot["tool_bindings"] = {"check_lead": {}}
    host._snapshot["flow"]["nodes"][0]["functions"] = [
        {
            "name": "check_lead",
            "transition_to": {
                "field": "status",
                "cases": {"qualified": "closing", "callback": "closing"},
                "default": "opening",
            },
        }
    ]
    host._nodes["opening"]["functions"] = host._snapshot["flow"]["nodes"][0]["functions"]

    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._pipecat_flow = compile_pipecat_flow(
        host._snapshot,
        handlers={"check_lead": host._pipecat_tool_proxy("check_lead")},
    )
    node = host._node("opening")
    check = next(function for function in node["functions"] if function.name == "check_lead")
    assert check.properties == {}


@pytest.mark.asyncio
async def test_native_branch_function_routes_from_registered_tool_result():
    host = _host()
    tool = {
        "description": "Check lead qualification.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }
    host._snapshot["_resolved"]["tools"]["check_lead"] = {"definition": tool}
    host._snapshot["flow"]["nodes"][0]["functions"] = [
        {
            "name": "check_lead",
            "transition_to": {
                "field": "status",
                "cases": {"qualified": "closing"},
                "default": "opening",
            },
        }
    ]
    host._nodes["opening"]["functions"] = host._snapshot["flow"]["nodes"][0]["functions"]

    async def configured_handler(args, _manager):
        assert args == {}
        return {"status": "qualified"}, TRANSITION_IN_YAML

    host._handler = lambda _name: configured_handler
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._pipecat_flow = compile_pipecat_flow(
        host._snapshot,
        handlers={"check_lead": host._pipecat_tool_proxy("check_lead")},
    )
    node = host._node("opening")
    check = next(function for function in node["functions"] if function.name == "check_lead")
    result, destination = await check.handler({}, SimpleNamespace())

    assert result == {"status": "qualified"}
    assert destination["name"] == "closing"


def test_user_aggregator_turn_filter_is_opt_in_and_uses_native_strategy():
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.turns.user_turn_strategies import FilterIncompleteUserTurnStrategies
    from voice_runtime.execution.native_helpers import build_user_aggregator_params

    vad = SileroVADAnalyzer(sample_rate=16000)
    base = build_user_aggregator_params(
        {"call_limits": {"interruptions_enabled": True, "idle_timeout_secs": 8}}, vad
    )
    experiment = build_user_aggregator_params(
        {
            "call_limits": {"interruptions_enabled": True, "idle_timeout_secs": 8},
            "filter_incomplete_user_turns": True,
        },
        vad,
    )

    assert not isinstance(base.user_turn_strategies, FilterIncompleteUserTurnStrategies)
    assert isinstance(experiment.user_turn_strategies, FilterIncompleteUserTurnStrategies)


def test_change_node_is_not_advertised_on_node_without_transitions():
    host = _host()

    node = host._node("closing")

    assert node["functions"] == []


def test_compiled_flow_uses_native_pre_post_actions_and_registry_action_handler():
    host = _host()
    host._nodes["opening"]["pre_actions"] = [
        {"type": "tts_say", "text": "One moment.", "append_text_to_context": False},
        {"type": "function", "handler": "lookup"},
    ]
    host._nodes["opening"]["post_actions"] = [
        {"type": "tts_say", "text": "Done.", "append_text_to_context": True}
    ]
    host._snapshot["flow"]["nodes"][0].update(host._nodes["opening"])
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._pipecat_flow = compile_pipecat_flow(
        host._snapshot,
        handlers={"_run_configured_node_action": host._run_configured_node_action},
    )

    node = host._node("opening")

    assert node["pre_actions"][0] == {
        "type": "tts_say",
        "text": "One moment.",
        "append_text_to_context": False,
    }
    assert node["pre_actions"][1]["type"] == "function"
    assert callable(node["pre_actions"][1]["handler"])
    assert node["pre_actions"][1]["binding_key"] == "lookup"
    assert node["post_actions"][0]["type"] == "tts_say"


@pytest.mark.asyncio
async def test_operator_fact_slot_tool_writes_only_its_validated_state_key():
    host = _host()
    host._snapshot["fact_slots"] = [
        {
            "key": "budget",
            "description": "the caller's budget in dollars",
            "value_type": "integer",
            "minimum": 1,
            "maximum": 10000,
            "nodes": ["opening"],
        }
    ]
    host._nodes["opening"]["prompt"] = "When given a budget, call #record_budget."
    host._snapshot["flow"]["nodes"][0]["prompt"] = host._nodes["opening"]["prompt"]
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._pipecat_flow = compile_pipecat_flow(host._snapshot)
    node = host._node("opening")
    assert "call record_budget." in node["role_message"]
    assert "#record_budget" not in node["role_message"]
    capture = next(function for function in node["functions"] if function.name == "record_budget")
    manager = SimpleNamespace(state={"existing_fact": "keep"})

    result = await capture.handler({"value": 2500}, manager)
    rejected = await capture.handler({"value": 0}, manager)

    assert result == {"status": "ok", "key": "budget", "value": 2500}
    assert rejected["status"] == "error"
    assert manager.state == {"existing_fact": "keep", "budget": 2500}
    from pipecat.flows import FlowManager

    rendered = FlowManager._render_node(
        manager,
        "closing",
        {"role_message": "Confirmed budget: {{budget}}", "task_messages": []},
    )
    assert rendered["role_message"] == "Confirmed budget: 2500"


@pytest.mark.asyncio
async def test_change_node_returns_native_node_config_only_for_saved_transition():
    host = _host()
    host.flow = SimpleNamespace(current_node="opening")
    handler = host._handler("change_node")

    result, next_node = await handler({"node": "closing"}, None)

    assert result == {"status": "ok", "node": "closing"}
    assert next_node["name"] == "closing"
    assert next_node["context_strategy"] == ContextStrategyConfig(strategy=ContextStrategy.RESET)
    assert await handler({"node": "unknown"}, None) == {
        "status": "error",
        "error": "Transition is not allowed",
    }


def test_legacy_change_node_objective_maps_to_native_transition_name():
    host = _host()
    host._nodes["opening"]["prompt"] = "When ready, use change_node to move to closing."
    host._snapshot["flow"]["nodes"][0]["prompt"] = host._nodes["opening"]["prompt"]
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    host._pipecat_flow = compile_pipecat_flow(host._snapshot)
    node = host._node("opening")

    assert "change_node" not in node["role_message"]
    assert "go_to_closing" in node["role_message"]


@pytest.mark.parametrize("precompiled", [False, True])
def test_explicit_transition_is_not_duplicated_by_allowed_transitions(precompiled):
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow
    from voice_shared.compiler import compile_flow_json

    snapshot = _host()._snapshot
    snapshot["flow"]["nodes"][0]["functions"] = [
        {
            "name": "go_to_closing",
            "description": "Explicit closing transition",
            "transition_only": True,
            "transition_to": "closing",
        }
    ]
    compiled = compile_flow_json(snapshot)
    assert [f["name"] for f in compiled["nodes"]["opening"]["functions"]] == ["go_to_closing"]
    assert (
        compiled["nodes"]["opening"]["functions"][0]["description"] == "Explicit closing transition"
    )
    if precompiled:
        snapshot["_compiled_flow"] = compiled
    node = compile_pipecat_flow(snapshot).node("opening")
    assert [f.name for f in node["functions"]] == ["go_to_closing"]
