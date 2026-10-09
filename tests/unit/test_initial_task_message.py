"""Opening requests must contain an operator-authored user instruction."""

import pytest
from pydantic import ValidationError
from voice_api.core.validation import public_validation_errors
from voice_runtime.contracts.agent import FlowConfig


def flow(messages, respond=True):
    return {
        "initial_node": "greeting",
        "nodes": [
            {
                "id": "greeting",
                "terminal": True,
                "respond_immediately": respond,
                "task_messages": messages,
            }
        ],
    }


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "system", "content": "Greet"}],
        [{"role": "developer", "content": "Greet"}],
        [{"role": "user", "content": "  "}],
    ],
)
def test_initial_response_requires_nonempty_user_task(messages):
    with pytest.raises(ValidationError) as caught:
        FlowConfig.model_validate(flow(messages))
    error = caught.value.errors()[0]
    assert error["type"] == "initial_user_task_required"
    assert error["loc"] == ("nodes", 0, "task_messages")
    assert "Add a nonempty user task message" in public_validation_errors(caught.value)[0]["msg"]


def test_operator_opening_is_kept_and_waiting_node_needs_no_task():
    message = {"role": "user", "content": "Introduce Ritu, then wait."}
    assert (
        FlowConfig.model_validate(flow([message])).nodes[0].task_messages[0].content
        == message["content"]
    )
    assert FlowConfig.model_validate(flow([], False)).nodes[0].task_messages == []


def test_legacy_version_readable_but_write_rejected():
    from voice_api.schemas.agent import AgentVersionResponse, RevisionBody

    config = {"name": "Legacy", "flow": flow([])}
    result = AgentVersionResponse(
        id="legacy", version=1, revision=1, status="draft", config=config, note=None
    )
    assert result.config.flow.nodes[0].task_messages == []
    with pytest.raises(ValidationError):
        RevisionBody(revision=1, config=config)


@pytest.mark.parametrize("old_stt", [False, True])
async def test_clone_published_version_without_opening_task_preserves_draft(monkeypatch, old_stt):
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from voice_api.models import AgentVersion
    from voice_api.services.publication_service import clone_version, sync_bindings
    from voice_runtime.contracts import AgentConfig

    source_config = {"name": "Legacy", "flow": flow([])}
    if old_stt:
        source_config["stt"] = {"provider": "sarvam", "model": "saaras:v3"}
    source = AgentVersion(
        id="source",
        agent_id="agent",
        version=2,
        revision=5,
        status="published",
        config=deepcopy(source_config),
    )
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[source, object(), source]),
        scalar=AsyncMock(return_value=2),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        add=Mock(),
        add_all=Mock(),
        flush=AsyncMock(),
        execute=AsyncMock(),
        commit=AsyncMock(),
    )
    monkeypatch.setattr("voice_api.core.config.get_settings", lambda: SimpleNamespace(env="dev"))
    result = await clone_version(session, "source", "agent", 5)
    draft = session.add.call_args.args[0]
    assert result["status"] == "draft"
    assert result["version"] == 3
    assert draft.parent_id == source.id
    expected = deepcopy(source_config)
    if old_stt:
        expected["stt"]["model"] = "saaras:v3-realtime"
    assert draft.config == expected
    assert source.status == "published"
    assert source.config == source_config
    with pytest.raises(ValidationError):
        AgentConfig.model_validate(draft.config)
    with pytest.raises(ValidationError):
        await sync_bindings(session, draft)
    draft.config["flow"]["nodes"][0]["task_messages"] = [
        {"role": "user", "content": "Introduce yourself, then wait."}
    ]
    AgentConfig.model_validate(draft.config)
    assert source.config == source_config
