"""Pin the installed Pipecat Flows APPEND/RESET message behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.flows import ContextStrategy, ContextStrategyConfig, FlowManager
from pipecat.frames.frames import LLMMessagesAppendFrame, LLMMessagesUpdateFrame
from pipecat.processors.aggregators.llm_context import NOT_GIVEN, LLMContext


@pytest.mark.parametrize(
    ("strategy", "frame_type", "expected_history"),
    [
        (ContextStrategy.APPEND, LLMMessagesAppendFrame, True),
        (ContextStrategy.RESET, LLMMessagesUpdateFrame, False),
    ],
)
async def test_transition_message_frame_preserves_or_replaces_transcript(
    strategy, frame_type, expected_history
):
    queued = AsyncMock()
    manager = SimpleNamespace(_worker=SimpleNamespace(queue_frames=queued))
    context = LLMContext(
        [
            {"role": "user", "content": "I need a new store."},
            {"role": "assistant", "content": "What platform are you using?"},
        ]
    )

    await FlowManager._update_llm_context(
        manager,
        role_message="E-commerce sales assistant",
        role_messages=None,
        task_messages=[{"role": "user", "content": "Discuss pricing."}],
        functions=NOT_GIVEN,
        strategy=ContextStrategyConfig(strategy=strategy),
    )

    frames = queued.await_args.args[0]
    message_frame = next(frame for frame in frames if isinstance(frame, frame_type))
    if isinstance(message_frame, LLMMessagesUpdateFrame):
        context.set_messages(message_frame.messages)
    else:
        context.add_messages(message_frame.messages)
    contents = [message["content"] for message in context.get_messages()]
    assert ("I need a new store." in contents) is expected_history
    assert "Discuss pricing." in contents
