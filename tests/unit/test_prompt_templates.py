import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.flows import FlowManager
from pydantic import ValidationError
from voice_api.services.prompt_preview import preview_prompt
from voice_runtime.contracts.agent import AgentConfig, FactSlotConfig
from voice_runtime.contracts.evidence import validate_evidence_record
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.flow_manager import TracedFlowManager
from voice_shared.compiler import compile_flow_json
from voice_shared.prompt_templates import (
    initialize_facts,
    parse_template,
    render_node,
    render_template,
    validate_template,
    variable_types,
)


def config(**changes):
    cfg = {
        "name": "Test",
        "contact_variables": ["language"],
        "fact_slots": [{"key": "preferred_language", "description": "Confirmed language"}],
        "system_prompt": "Speak [ {{language}} | {{preferred_language}} ].",
        "flow": {
            "initial_node": "end",
            "prompt_composition": "global_plus_node",
            "nodes": [
                {
                    "id": "end",
                    "terminal": True,
                    "respond_immediately": False,
                    "role_message": "Name {{language}}",
                    "task_messages": [],
                }
            ],
        },
    }
    cfg.update(changes)
    return AgentConfig.model_validate(cfg)


@pytest.mark.parametrize(
    "kind,value",
    [
        ("string", "hello"),
        ("integer", 3),
        ("number", 1.2),
        ("boolean", True),
        ("boolean", False),
        ("integer", ""),
    ],
)
def test_defaults(kind, value):
    slot = FactSlotConfig(key="fact", description="Fact", value_type=kind, default_value=value)
    assert slot.default_value == value
    assert initialize_facts({}, [slot.model_dump()]) == {"fact": value}
    assert (
        initialize_facts({"fact": "already recorded"}, [slot.model_dump()])["fact"]
        == "already recorded"
    )


@pytest.mark.parametrize(
    "kind,value",
    [
        ("string", None),
        ("integer", True),
        ("boolean", 1),
        ("number", float("inf")),
        ("number", float("nan")),
    ],
)
def test_invalid_defaults(kind, value):
    with pytest.raises(ValidationError):
        FactSlotConfig(key="fact", description="Fact", value_type=kind, default_value=value)


def test_constraints_and_empty_marker():
    assert (
        FactSlotConfig(key="f", description="Fact", value_type="integer", minimum=2).default_value
        == ""
    )
    with pytest.raises(ValidationError):
        FactSlotConfig(
            key="f", description="Fact", value_type="integer", minimum=2, default_value=1
        )
    with pytest.raises(ValidationError):
        FactSlotConfig(key="f", description="Fact", enum=["yes"], default_value="no")
    with pytest.raises(ValueError):
        FactSlotConfig(key="f", description="Fact", value_type="boolean").validate_value("")


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", "fallback"),
        ("  \t", "fallback"),
        (0, "fallback"),
        ("0", "0"),
        (-2, "-2"),
        ("Marathi", "Marathi"),
    ],
)
def test_rightmost_nonempty(value, expected):
    output, records = render_template(
        "[ {{a}} | {{b}} ]", {"a": "fallback", "b": value}, {"a": "string", "b": "number"}
    )
    assert output == expected
    assert len(records) == 1


def test_chains_all_empty_and_no_recursive_render():
    output, records = render_template(
        "[ {{a}} | {{b}} | {{c}} ]", dict(a="", b=0, c=" "), dict.fromkeys("abc", "string")
    )
    assert output == "" and records[0]["outcome"] == "all_empty"
    assert render_template("{{a}}", {"a": "{{b}}"}, {"a": "string"})[0] == "{{b}}"
    assert render_template("{{a}}", {"a": False}, {"a": "boolean"})[0] == "False"


@pytest.mark.parametrize(
    "text",
    [
        "[ {{a}} ]",
        "[ {{a}} | literal ]",
        "[ literal | {{a}} ]",
        "[ {{a}} | {{b}}",
        "[ [ {{a}} | {{b}} ] ]",
        "{{a",
    ],
)
def test_malformed(text):
    with pytest.raises(ValueError):
        parse_template(text)


def test_unknown_boolean_null_and_escapes():
    with pytest.raises(ValueError, match="Unknown"):
        validate_template("{{missing}}", {})
    with pytest.raises(ValueError, match="Boolean"):
        validate_template("[ {{a}} | {{b}} ]", {"a": "string", "b": "boolean"})
    with pytest.raises(ValueError, match="null"):
        render_template("{{a}}", {"a": None}, {"a": "string"})
    text = r"\[ {{a}} | {{b}} ] and \{{a}} [literal] x | y"
    assert render_template(text, {}, {})[0] == "[ {{a}} | {{b}} ] and {{a}} [literal] x | y"


def test_validation_locations_and_legacy_reading():
    with pytest.raises(ValidationError, match=r"system_prompt.*Unknown"):
        config(system_prompt="{{missing}}")
    with pytest.raises(ValidationError, match="collide"):
        config(fact_slots=[{"key": "language", "description": "Fact"}])
    saved = config().model_dump()
    saved["system_prompt"] = "{{historical_unknown}}"
    assert AgentConfig.model_validate(saved, context={"read_legacy_config": True})


def test_preview_runtime_parity_and_no_mutation():
    cfg = config()
    original = deepcopy(cfg.model_dump())
    preview = preview_prompt(cfg, "end", {"language": "mr-IN"}, {})
    node = compile_flow_json(original)["nodes"]["end"]
    state = initialize_facts({"language": "mr-IN"}, original["fact_slots"])
    rendered, records = render_node(node, state, variable_types(original))
    assert preview["rendered"]["role_message"] == rendered["role_message"]
    assert preview["resolution"][0]["selected_key"] == records[0]["selected_key"] == "language"
    assert cfg.model_dump() == original
    assert "mr-IN" in preview["rendered"]["role_message"]
    empty = preview_prompt(cfg, "end", {"language": None}, {})
    assert empty["resolution"][0]["outcome"] == "all_empty"
    assert empty["resolution"][0]["candidates"][0]["source"]["kind"] == "contact"
    with pytest.raises(ValueError, match="exposed"):
        preview_prompt(cfg, "end", {"secret": "value"}, {})


async def test_node_entry_only_and_evidence(monkeypatch):
    cfg = config().model_dump()
    captured, dispatched = [], []
    tracker = ExchangeTracker("run-1", SimpleNamespace(submit=captured.append))
    flow = object.__new__(TracedFlowManager)
    flow._snapshot, flow._state = cfg, initialize_facts({"language": "mr-IN"}, cfg["fact_slots"])
    flow.fact_sources = {"preferred_language": {"kind": "default"}}
    flow._current_node = None
    flow._classifier_runner = AsyncMock(return_value=None)
    flow.tracker, flow._transition_tool_id = tracker, None
    flow.context_generation, flow.termination = 0, None
    node = compile_flow_json(cfg)["nodes"]["end"]

    async def dispatch(self, node_id, rendered):
        assert self._render_node(node_id, rendered) is rendered
        dispatched.append(rendered)

    monkeypatch.setattr(FlowManager, "_set_node", dispatch)
    await flow._set_node("end", node)
    assert "mr-IN" in dispatched[0]["role_message"]
    flow._state["preferred_language"] = "hi-IN"
    flow.fact_sources["preferred_language"] = {"kind": "record_tool", "invocation_id": "tool-1"}
    assert "hi-IN" not in dispatched[0]["role_message"]
    await flow._set_node("end", node)
    assert "hi-IN" in dispatched[1]["role_message"]
    visits = [r for r in captured if r["kind"] == "flow_visit_started"]
    assert len(visits) == 2
    assert (
        visits[1]["prompt_resolution"]["records"][0]["candidates"][1]["source"]["invocation_id"]
        == "tool-1"
    )
    validate_evidence_record(visits[1])
    operation = tracker.start_operation("fake-model", "llm")
    assert operation["attributes"]["node_visit_id"] == visits[1]["visit_id"]
    assert "prompt_resolution" not in operation
    tracker.finish_operation(operation, "completed")
    assert (
        "preferred_language" not in node["role_message"]
        or "{{preferred_language}}" in node["role_message"]
    )


async def test_record_tool_updates_provenance_and_fresh_runs_reset():
    from voice_runtime.execution.native import NativePipelineHost

    cfg = config().model_dump()
    cfg["_resolved"] = {"tools": {}}
    host = NativePipelineHost("run-1", Path("unused"), SimpleNamespace())
    host._snapshot = cfg
    host._nodes = {n["id"]: n for n in cfg["flow"]["nodes"]}
    tool = next(f for f in host._node("end")["functions"] if f.name == "record_preferred_language")
    manager = SimpleNamespace(
        state=initialize_facts({}, cfg["fact_slots"]),
        fact_sources={},
        active_tool_invocation_id="tool-1",
    )
    assert manager.state["preferred_language"] == ""
    result = await tool.handler({"value": "hi-IN"}, manager)
    assert result["status"] == "ok"
    assert manager.state["preferred_language"] == "hi-IN"
    assert manager.fact_sources["preferred_language"] == {
        "kind": "record_tool",
        "invocation_id": "tool-1",
    }
    assert initialize_facts({}, cfg["fact_slots"])["preferred_language"] == ""


async def test_classifier_result_is_not_rendered_as_a_template(monkeypatch):
    flow = object.__new__(TracedFlowManager)
    flow._snapshot = config().model_dump()
    flow._state = {"language": "mr-IN", "preferred_language": ""}
    flow._current_node = None
    message = {"role": "system", "content": "Caller mentioned {{not_a_template}}"}
    flow._classifier_runner = AsyncMock(return_value=("result", message))
    flow.tracker = SimpleNamespace(start_visit=lambda *args: None, end_visit=lambda *args: None)
    flow.context_generation, flow.termination, flow._transition_tool_id = 0, None, None
    dispatched = []

    async def dispatch(self, node_id, node):
        dispatched.append(node)

    monkeypatch.setattr(FlowManager, "_set_node", dispatch)
    await flow._set_node("end", compile_flow_json(flow._snapshot)["nodes"]["end"])
    assert dispatched[0]["task_messages"][-1] == message


def test_shared_editor_parser_fixtures():
    fixtures = json.loads(
        (Path(__file__).parents[2] / "contracts/prompt-template-fixtures.json").read_text(
            encoding="utf-8"
        )
    )
    for case in fixtures:
        if case.get("error"):
            with pytest.raises(ValueError):
                parse_template(case["text"])
        else:
            assert parse_template(case["text"]) == case["tokens"]


async def test_evidence_ingestion_replays_and_conflicts():
    from fastapi import HTTPException
    from voice_api.api.v1.endpoints.evidence import store_record
    from voice_api.models import Run, TraceSpan

    cfg = config().model_dump()
    captured = []
    tracker = ExchangeTracker(
        "run-1", SimpleNamespace(submit=captured.append), secrets=("provider-secret",)
    )
    _, refs = render_node(
        compile_flow_json(cfg)["nodes"]["end"],
        {"language": "provider-secret", "preferred_language": ""},
        variable_types(cfg),
    )
    tracker.start_visit(
        "end",
        prompt_resolution={
            "state": "recorded",
            "node_key": "end",
            "rendered_at": "2026-10-09T10:00:00Z",
            "records": refs,
        },
    )
    record = validate_evidence_record(captured[0])
    assert "provider-secret" not in json.dumps(captured)
    objects = {(Run, "run-1"): SimpleNamespace(resolved_config=cfg)}

    class Session:
        async def get(self, model, identity):
            return objects.get((model, identity))

        def add(self, row):
            objects[type(row), row.id] = row

        async def flush(self):
            pass

    session = Session()
    await store_record(session, "run-1", record)
    await store_record(session, "run-1", record)
    stored = objects[TraceSpan, record.span_id]
    assert stored.input_payload["prompt_resolution"]["records"][0]["selected_key"] == "language"
    altered = record.model_copy(deep=True)
    altered.prompt_resolution.records[0].selected_key = "preferred_language"
    with pytest.raises(HTTPException) as error:
        await store_record(session, "run-1", altered)
    assert error.value.status_code == 409


async def test_preview_endpoint_is_read_only_and_scoped():
    from fastapi import HTTPException
    from voice_api.api.v1.endpoints.agents import prompt_preview
    from voice_api.schemas.agent import PromptPreviewBody

    session = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace()), commit=AsyncMock())
    body = PromptPreviewBody(config=config(), node_id="end", contact_values={"language": "mr-IN"})
    response = await prompt_preview("allowed-version", body, session, None)
    assert "mr-IN" in response["rendered"]["role_message"]
    session.commit.assert_not_called()
    session.get.return_value = None  # Tenant-scoped sessions hide another org's row.
    with pytest.raises(HTTPException) as error:
        await prompt_preview("other-org-version", body, session, None)
    assert error.value.status_code == 404


def test_action_text_and_task_messages_use_same_resolution():
    node = {
        "role_message": "[ {{a}} | {{b}} ]",
        "task_messages": [{"role": "user", "content": "{{b}}"}],
        "pre_actions": [{"type": "tts_say", "text": "[ {{b}} | {{a}} ]"}],
        "post_actions": [{"type": "tts_say", "text": r"\{{b}}"}],
    }
    rendered, records = render_node(node, {"a": "", "b": "hi"}, dict.fromkeys(["a", "b"], "string"))
    assert rendered["role_message"] == "hi"
    assert rendered["task_messages"][0]["content"] == "hi"
    assert rendered["pre_actions"][0]["text"] == "hi"
    assert rendered["post_actions"][0]["text"] == "{{b}}"
    assert [r["field"] for r in records] == [
        "role_message",
        "task_messages.0.content",
        "pre_actions.0.text",
    ]
