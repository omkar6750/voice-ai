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
