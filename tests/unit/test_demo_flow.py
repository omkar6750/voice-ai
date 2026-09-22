import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def demo():
    path = Path(__file__).resolve().parents[2] / "scripts/demo_call.py"
    spec = importlib.util.spec_from_file_location("demo_call_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_node_tool_has_explicit_enum_and_transitions():
    module = demo()
    node = module.build_node("greeting")
    tool = node["functions"][0]
    schema = tool.to_function_schema().to_default_dict()
    assert schema["parameters"]["properties"]["node"] == {
        "type": "string",
        "enum": list(module.VALID_NODES),
    }
    result, next_node = await tool.handler(
        {"node": "discovery"}, SimpleNamespace(current_node="greeting")
    )
    assert result["status"] == "success"
    assert next_node["name"] == "discovery"
    assert next_node["respond_immediately"] is True


@pytest.mark.asyncio
async def test_malformed_node_argument_does_not_crash():
    module = demo()
    result, node = await module.change_node({"node": {"name": "discovery"}}, None)
    assert "error" in result
    assert node is None


@pytest.mark.asyncio
async def test_tools_suite_initialization_and_handlers():
    module = demo()
    from pipecat.processors.aggregators.llm_context import LLMContext
    from voice_runtime.providers.demo import DemoProviderSettings

    settings = DemoProviderSettings(
        cartesia_api_key="fake",
        sarvam_api_key="fake",
        groq_api_key="fake",
    )
    context = LLMContext([{"role": "user", "content": "Hello"}])
    sales_state = {"whatsapp_window_open": False, "caller_name": "TestUser"}
    tools = module._make_tools(settings, context, "+15551234567", sales_state=sales_state)

    tool_names = [t.name for t in tools]
    assert "change_node" in tool_names
    assert "end_call" in tool_names
    assert "send_whatsapp_template" in tool_names
    assert "classify_jev" in tool_names
    assert "classify_llm" in tool_names
    assert "classify_lead" in tool_names

    # Test end_call
    end_tool = next(t for t in tools if t.name == "end_call")
    res, _ = await end_tool.handler({}, SimpleNamespace(current_node="closing"))
    assert res["status"] == "call_ended"

    classification = {
        "lead_temperature": {"choice": "warm", "confidence": 0.8},
        "service_fit": {"choice": "strong_fit", "confidence": 0.9},
        "tone": {"choice": "receptive", "confidence": 0.9},
    }
    module.run_jev_classification = AsyncMock(return_value=classification)
    module.run_llm_classification = AsyncMock(return_value=classification)

    jev_tool = next(t for t in tools if t.name == "classify_jev")
    res_jev, _ = await jev_tool.handler({}, SimpleNamespace(current_node="qualification"))
    assert "lead_temperature" in res_jev
    assert "service_fit" in res_jev
    assert "tone" in res_jev

    llm_tool = next(t for t in tools if t.name == "classify_llm")
    res_llm, _ = await llm_tool.handler({}, SimpleNamespace(current_node="qualification"))
    assert "lead_temperature" in res_llm
    assert "service_fit" in res_llm
    assert "tone" in res_llm
