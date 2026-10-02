import pytest
from voice_runtime.execution.lead_routing import followup_route


@pytest.mark.parametrize(
    "temperature,fit,tone,expected",
    [
        ("hot", "strong_fit", "receptive", "hot_followup"),
        ("hot", "strong_fit", "hesitant", "warm_nurture"),
        ("warm", "possible_fit", "receptive", "warm_nurture"),
        ("cold", "strong_fit", "resistant", "cold_check"),
        ("hot", "poor_fit", "receptive", "fit_clarification"),
    ],
)
def test_followup_route(temperature, fit, tone, expected):
    assert (
        followup_route(dict(lead_temperature=temperature, service_fit=fit, tone=tone)) == expected
    )


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"status": "error"},
        {"lead_temperature": "hot"},
        {"lead_temperature": "invented", "service_fit": "strong_fit", "tone": "receptive"},
    ],
)
def test_invalid_classifier_does_not_transition(result):
    assert followup_route(result) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,changed,expected",
    [
        (
            {"lead_temperature": "hot", "service_fit": "strong_fit", "tone": "receptive"},
            False,
            "hot_followup",
        ),
        ({"status": "error"}, False, "stay"),
        ({"lead_temperature": "hot", "service_fit": "strong_fit", "tone": "receptive"}, True, None),
    ],
)
async def test_proxy_routes_after_result_and_fences_changed_node(result, changed, expected):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from pipecat.flows.types import NO_RESPONSE, TRANSITION_IN_YAML
    from voice_runtime.execution.native_host import NativePipelineHost

    manager = SimpleNamespace(current_node="discovery_and_qualify")

    async def handler(params, flow_manager):
        if changed:
            flow_manager.current_node = "closing"
        return result

    host = SimpleNamespace(
        _snapshot={"classifier": {"routing_policy": "lead_followup"}},
        _handler=lambda name: handler,
        tracker=Mock(),
    )
    actual, transition = await NativePipelineHost._pipecat_tool_proxy(host, "classify_lead")(
        manager
    )
    if changed:
        assert transition is NO_RESPONSE
    else:
        assert transition is TRANSITION_IN_YAML
        assert actual["followup_route"] == expected


@pytest.mark.asyncio
async def test_routing_classifier_waits_for_actual_result(monkeypatch):
    from types import SimpleNamespace

    from voice_runtime.execution import tool_dispatch

    result = {"lead_temperature": "hot", "service_fit": "strong_fit", "tone": "receptive"}

    async def classify(**kwargs):
        return result

    monkeypatch.setattr(tool_dispatch, "run_selected_classifier", classify)
    monkeypatch.setattr(tool_dispatch, "_extract_transcript", lambda *args: "User has a project")
    host = SimpleNamespace(
        _snapshot={"classifier": {"routing_policy": "lead_followup"}},
        settings=SimpleNamespace(),
        tracker=SimpleNamespace(),
        _is_nonblocking_tool=tool_dispatch.NativeToolDispatch._is_nonblocking_tool,
    )
    actual = await tool_dispatch.NativeToolDispatch._handler(host, "classify_lead")(
        {}, SimpleNamespace()
    )
    assert actual == {**result, "classification_key": "hot|strong_fit|receptive"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "classification,expected",
    [
        (
            {"lead_temperature": "hot", "service_fit": "strong_fit", "tone": "receptive"},
            "hot_followup",
        ),
        ({"status": "error"}, None),
    ],
)
async def test_configured_pipecat_branch_executes_real_contract(classification, expected):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from voice_runtime.contracts.agent import FlowConfig
    from voice_runtime.execution.native_host import NativePipelineHost
    from voice_runtime.execution.pipecat_flow import compile_pipecat_flow

    targets = ["hot_followup", "warm_nurture", "cold_check", "fit_clarification"]
    nodes = [
        {
            "id": "discovery",
            "role_message": "Discover",
            "functions": [
                {
                    "name": "classify_lead",
                    "transition_to": {"field": "followup_route", "cases": {x: x for x in targets}},
                }
            ],
        }
    ]
    nodes += [{"id": x, "role_message": x, "terminal": True} for x in targets]
    cfg = {
        "flow": {"initial_node": "discovery", "nodes": nodes},
        "classifier": {"routing_policy": "lead_followup"},
    }
    FlowConfig.model_validate(cfg["flow"])

    async def handler(params, manager):
        return classification

    host = SimpleNamespace(_snapshot=cfg, _handler=lambda name: handler, tracker=Mock())
    flow = compile_pipecat_flow(
        cfg,
        handlers={"classify_lead": NativePipelineHost._pipecat_tool_proxy(host, "classify_lead")},
    )
    function = flow.node("discovery")["functions"][0]
    result, destination = await function.handler({}, SimpleNamespace(current_node="discovery"))
    assert result["followup_route"] == (expected or "stay")
    assert (destination is None) == (expected is None)
    if expected:
        assert destination == flow.node(expected)
