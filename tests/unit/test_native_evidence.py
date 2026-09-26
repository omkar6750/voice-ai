"""New live-call evidence must be accepted by the versioned ingestion contract."""

from types import SimpleNamespace

from voice_api.api.v1.endpoints import calls
from voice_api.schemas.call import StartCallBody
from voice_runtime.contracts.evidence import EvidenceBatch
from voice_runtime.execution.exchange import ExchangeTracker
from voice_runtime.execution.native import NativePipelineHost


class MemorySink:
    def __init__(self):
        self.records = []

    def submit(self, record):
        self.records.append(record)


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
    tracker.tool_result(invocation, {"status": "ok"}, is_final=True)
    tracker.end_tool(invocation, "completed", {"status": "ok"})
    tracker.finish_operation(llm, "completed", output_payload={"text": "Hello"})
    tracker.end_visit("completed")
    tracker.start_visit("discovery", invocation)
    tracker.consume_results(greeting)
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
        "tool_ended",
        "tool_result_consumed",
    }


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
                            "properties": {"node": {"type": "string"}},
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
            "respond_immediately": True,
        }
    }
    node = host._node("greeting")
    assert node["role_message"] == "Global"
    assert node["task_messages"] == [{"role": "user", "content": "Say hello"}]
    assert [tool.name for tool in node["functions"]] == ["change_node"]
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
