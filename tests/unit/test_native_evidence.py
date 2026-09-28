"""New live-call evidence must be accepted by the versioned ingestion contract."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import voice_runtime.execution.native as native_module
from pipecat.processors.aggregators.llm_context import LLMContext
from voice_api.api.v1.endpoints import calls
from voice_api.schemas.call import StartCallBody
from voice_runtime.contracts.evidence import EvidenceBatch
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.native import (
    NativePipelineHost,
    build_whatsapp_template_payload,
    render_opening,
    whatsapp_template_header_component,
)


class MemorySink:
    def __init__(self):
        self.records = []

    def submit(self, record):
        self.records.append(record)


def test_verbatim_opening_renders_whitelisted_state_and_nested_contact_values() -> None:
    rendered = render_opening(
        "Hello {{ contact.name }}, this is about {{campaign}}.",
        {"contact": {"name": "Maria"}, "campaign": "summer"},
    )
    assert rendered == "Hello Maria, this is about summer."


def test_verbatim_opening_rejects_unavailable_state() -> None:
    with pytest.raises(ValueError, match="unavailable variable"):
        render_opening("Hello {{phone_number}}", {"name": "Maria"})


def test_whatsapp_template_header_uses_exact_meta_media_id() -> None:
    assert whatsapp_template_header_component({"format": "IMAGE", "media_id": "74506"}) == {
        "type": "header",
        "parameters": [{"type": "image", "image": {"id": "74506"}}],
    }


def test_whatsapp_template_header_rejects_incomplete_media_reference() -> None:
    with pytest.raises(ValueError, match="header configuration is invalid"):
        whatsapp_template_header_component({"format": "IMAGE", "media_id": ""})


def test_whatsapp_send_payload_keeps_meta_id_language_and_body_order() -> None:
    payload = build_whatsapp_template_payload(
        destination="919876543210",
        template_name="dialtone_followup",
        language="en_US",
        header={"format": "IMAGE", "media_id": "74506"},
        parameter_mappings={"2": "param_2", "1": "caller_name"},
        arguments={"caller_name": "Ava", "param_2": "Call summary"},
        caller_name="Ava",
    )
    template = payload["template"]
    assert template["language"] == {"code": "en_US"}
    assert template["components"][0]["parameters"][0]["image"] == {"id": "74506"}
    assert [item["text"] for item in template["components"][1]["parameters"]] == [
        "Ava",
        "Call summary",
    ]


def test_flow_tools_and_provider_evidence_round_trip():
    sink = MemorySink()
    tracker = ExchangeTracker("run-1", sink)
    greeting = tracker.begin("greeting")
    tracker.start_visit("greeting")
    llm = tracker.start_operation(
        "inference",
        "llm",
        provider="groq",
        model="model-1",
        input_payload={"messages": [{"role": "user", "content": "hello"}]},
    )
    invocation = tracker.start_tool(
        "change_node",
        "tool-v1",
        "function-1",
        {"node": "discovery"},
        llm["operation_id"],
    )
    result_id = tracker.tool_result(invocation, {"status": "ok"}, is_final=True)
    tracker.context_updated(invocation, result_id, context_message_index=3)
    tracker.end_tool(invocation, "completed", {"status": "ok"})
    tracker.finish_operation(llm, "completed", output_payload={"text": "Hello"})
    tracker.end_visit("completed")
    tracker.start_visit("discovery", invocation)
    consuming = tracker.start_operation("inference", "llm", model="model-2")
    tracker.consume_results(greeting, consuming["operation_id"])
    tracker.end_visit("completed")
    tracker.end_exchange("completed")
    records = EvidenceBatch(records=sink.records).records
    assert len(records) == len(sink.records)
    assert {record.kind for record in records} >= {
        "exchange",
        "exchange_ended",
        "flow_visit_started",
        "flow_visit_ended",
        "operation_started",
        "span",
        "tool_started",
        "tool_result",
        "tool_result_context_updated",
        "tool_ended",
        "tool_result_consumed",
    }


def test_caller_barge_in_interrupts_active_generation_and_tools_once():
    sink = MemorySink()
    tracker = ExchangeTracker("run-1", sink)
    tracker.begin("caller")
    speech = tracker.start_operation("caller speech", "speech")
    tracker.start_operation("transcription", "stt", parent_operation_id=speech["operation_id"])
    llm = tracker.start_operation("inference", "llm", parent_operation_id=speech["operation_id"])
    tts = tracker.start_operation("synthesis", "tts", parent_operation_id=llm["operation_id"])
    playback = tracker.start_operation(
        "serial playback", "playback", parent_operation_id=tts["operation_id"]
    )
    tool = tracker.start_tool(
        "send_whatsapp_template", "tool-v1", "function-1", {}, llm["operation_id"]
    )

    interruption_id = tracker.interrupt(
        source="caller", reason="caller_barge_in", frame_type="InterruptionFrame"
    )
    tracker.end_tool(tool, "cancelled", {"status": "cancelled"}, interruption_id=interruption_id)

    records = EvidenceBatch(records=sink.records).records
    interruption = next(record for record in records if record.kind == "interruption")
    assert interruption.interruption_id == interruption_id
    assert interruption.interrupted_operation_ids == [
        llm["operation_id"],
        tts["operation_id"],
        playback["operation_id"],
    ]
    assert interruption.interrupted_tool_invocation_ids == [tool]
    spans = [record for record in records if record.kind == "span"]
    assert {span.status for span in spans} == {"interrupted"}
    assert all(span.output_state == "interrupted" for span in spans)
    ended_tool = next(record for record in records if record.kind == "tool_ended")
    assert ended_tool.status == "cancelled"
    assert ended_tool.interruption_id == interruption_id
    assert len([record for record in records if record.kind == "interruption"]) == 1


def test_classifier_result_is_delivered_and_consumed_by_next_llm():
    sink = MemorySink()
    tracker = ExchangeTracker("run-1", sink)
    exchange = tracker.begin("greeting")
    classifier = tracker.start_classifier(
        phase="entry",
        node_key="discovery",
        classifier_type="llm",
        provider="groq",
        model="classifier-model",
        transcript="Caller: hello",
    )
    result_id, message = tracker.finish_classifier(
        classifier,
        "completed",
        {"lead_temperature": "warm"},
    )
    consuming = tracker.start_operation("inference", "llm", model="agent-model")
    tracker.consume_classifier_results([message], exchange, consuming["operation_id"])
    records = EvidenceBatch(records=sink.records).records
    assert {record.kind for record in records} >= {
        "classifier_result",
        "classifier_context_updated",
        "classifier_result_consumed",
    }
    assert any(
        record.result_id == result_id for record in records if record.kind == "classifier_result"
    )


@pytest.mark.asyncio
async def test_configured_node_classifier_runs_once_and_returns_context_message(
    monkeypatch, tmp_path
):
    host = NativePipelineHost("run-1", tmp_path, SimpleNamespace(groq_api_key="test-key"))
    host.context = LLMContext([{"role": "user", "content": "Caller: interested"}])
    sink = MemorySink()
    host.tracker = ExchangeTracker("run-1", sink)
    host.tracker.begin("greeting")
    host._snapshot = {
        "classifier": {
            "enabled": True,
            "classifier_type": "llm",
            "node_entries": ["greeting"],
            "node_exits": [],
            "llm": {
                "provider": "groq",
                "model": "classifier-model",
                "prompt": "Classify the call",
                "output_fields": {"lead_temperature": ["warm"]},
            },
        }
    }
    monkeypatch.setattr(
        native_module,
        "run_selected_classifier",
        AsyncMock(return_value={"lead_temperature": "warm"}),
    )

    first = await host._run_node_classifier("entry", "greeting")
    second = await host._run_node_classifier("entry", "greeting")

    assert first is not None and second is not None
    assert first[1]["role"] == "system"
    assert first[0] != second[0]
    assert sum(record["kind"] == "classifier_result" for record in sink.records) == 2


@pytest.mark.asyncio
async def test_classifier_cadence_runs_after_every_n_exchanges_and_updates_context(tmp_path):
    host = NativePipelineHost("run-1", tmp_path, object())
    host.context = LLMContext([])
    host.flow = SimpleNamespace(current_node="qualification")
    host._snapshot = {"classifier": {"enabled": True, "every_n_exchanges": 2}}
    host._exchange_count = 1
    host._run_node_classifier = AsyncMock(
        return_value=("result-1", {"role": "system", "content": "classifier result"})
    )

    await host._run_classifier_cadence()
    assert host._run_node_classifier.await_count == 0

    host._exchange_count = 2
    await host._run_classifier_cadence()

    host._run_node_classifier.assert_awaited_once_with("entry", "qualification", force=True)
    assert host.context.get_messages() == [{"role": "system", "content": "classifier result"}]


def test_node_configuration_is_scoped_to_published_bindings(tmp_path):
    host = NativePipelineHost("run-1", tmp_path, object())
    host._snapshot = {
        "system_prompt": "Global",
        "flow": {"initial_node": "greeting"},
        "_resolved": {
            "tools": {
                "change_node": {
                    "version_id": "tool-v1",
                    "definition": {
                        "description": "Move",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "node": {
                                    "type": "string",
                                    "description": "Destination node identifier",
                                }
                            },
                            "required": ["node"],
                        },
                    },
                }
            }
        },
    }
    host._nodes = {
        "greeting": {
            "id": "greeting",
            "prompt": "Say hello",
            "tool_bindings": ["change_node"],
            "transitions": ["closing"],
            "respond_immediately": True,
        }
    }
    node = host._node("greeting")
    assert node["role_message"] == "Global"
    assert node["task_messages"] == [{"role": "user", "content": "Say hello"}]
    assert [tool.name for tool in node["functions"]] == ["change_node"]
    assert node["functions"][0].description == "Move"
    assert node["functions"][0].properties["node"]["description"] == ("Destination node identifier")
    host._nodes["greeting"]["role_prompt"] = "Node role"
    host._nodes["greeting"]["context_strategy"] = "reset"
    overridden = host._node("greeting")
    assert overridden["role_message"] == "Node role"
    assert overridden["context_strategy"].strategy.value == "reset"


async def test_call_dispatch_leaves_claim_to_executor(monkeypatch):
    spawned = []

    async def queue(*_args):
        return SimpleNamespace(id="run-1"), SimpleNamespace(
            id="call-1", target_snapshot="+15551234567"
        )

    class Session:
        async def commit(self):
            pass

    monkeypatch.setattr(calls, "queue_call", queue)
    monkeypatch.setattr(calls, "get_settings", lambda: SimpleNamespace(operator_token="test"))
    monkeypatch.setattr(
        calls, "_spawn_call_task", lambda run, endpoint: spawned.append((run, endpoint))
    )
    result = await calls.start_call(
        StartCallBody(
            contact_id="contact-1",
            agent_version_id="version-1",
            endpoint_id="endpoint-1",
            dispatch=True,
        ),
        session=Session(),
        _=None,
    )
    assert result["status"] == "dispatching"
    assert spawned == [("run-1", "endpoint-1")]
