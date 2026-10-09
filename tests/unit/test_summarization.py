from voice_runtime.execution.summarization import (
    messages_to_keep_for_recent_exchanges,
    should_summarize,
    summary_source_is_current,
)


def test_summary_cadence_triggers_at_four_completed_exchanges_or_context_limit():
    assert (
        should_summarize(
            completed_exchanges=3,
            estimated_context_tokens=3071,
            every_n_exchanges=4,
            context_window_tokens=3072,
        )
        is None
    )
    assert (
        should_summarize(
            completed_exchanges=4,
            estimated_context_tokens=2000,
            every_n_exchanges=4,
            context_window_tokens=3072,
        )
        == "completed_exchange_threshold"
    )
    assert (
        should_summarize(
            completed_exchanges=1,
            estimated_context_tokens=3072,
            every_n_exchanges=4,
            context_window_tokens=3072,
        )
        == "context_token_threshold"
    )


def test_retention_keeps_two_complete_recent_exchanges_with_tool_messages():
    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "business"},
        {"role": "assistant", "content": "question"},
        {
            "role": "assistant",
            "tool_calls": [{"id": "t1", "function": {"name": "lookup"}}],
        },
        {"role": "tool", "tool_call_id": "t1", "content": "available"},
        {"role": "assistant", "content": "answer"},
        {"role": "user", "content": "goal"},
        {"role": "assistant", "content": "follow-up"},
        {"role": "user", "content": "timing"},
        {"role": "assistant", "content": "close"},
    ]

    assert messages_to_keep_for_recent_exchanges(messages, exchange_count=2) == 4


def test_retention_keeps_current_task_message_and_ignores_summary_as_user_turn():
    task = {"role": "system", "content": "Current node task"}
    messages = [
        {"role": "system", "content": "Base instructions"},
        {"role": "user", "content": "Conversation summary: old note"},
        {"role": "user", "content": "caller one"},
        {"role": "assistant", "content": "agent one"},
        task,
        {"role": "user", "content": "caller two"},
        {"role": "assistant", "content": "agent two"},
        {"role": "user", "content": "caller three"},
        {"role": "assistant", "content": "agent three"},
    ]

    assert (
        messages_to_keep_for_recent_exchanges(
            messages, exchange_count=2, active_task_messages=[task]
        )
        == 5
    )


def test_retention_keeps_all_messages_when_there_is_no_complete_exchange():
    messages = [
        {"role": "system", "content": "node task"},
        {"role": "user", "content": "caller is still speaking"},
    ]

    assert messages_to_keep_for_recent_exchanges(messages, exchange_count=2) == len(messages)


def test_summary_result_requires_same_generation_and_preserves_newer_tail():
    source = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "source turn"},
    ]
    with_appended_tail = [*source, {"role": "assistant", "content": "new answer"}]

    assert summary_source_is_current(
        expected_generation=3,
        current_generation=3,
        expected_prefix=source,
        current_messages=with_appended_tail,
    )
    assert not summary_source_is_current(
        expected_generation=3,
        current_generation=4,
        expected_prefix=source,
        current_messages=with_appended_tail,
    )
    assert not summary_source_is_current(
        expected_generation=3,
        current_generation=3,
        expected_prefix=source,
        current_messages=[*source[:1], {"role": "user", "content": "changed"}],
    )


class _FakeTracker:
    def __init__(self):
        self.current = None
        self.diagnostics = []

    def diagnostic(self, **details):
        self.diagnostics.append(details)


class _FakeSummarizer:
    def __init__(self):
        self._pending_summary_request_id = "request-1"
        self._auto_config = type(
            "AutoConfig", (), {"summary_config": type("SummaryConfig", (), {})()}
        )()
        self.applied = []
        self.handler = None

    async def _clear_summarization_state(self):
        pass

    def _validate_summary_context(self, _index):
        return True

    async def _apply_summary(self, summary, index):
        self.applied.append((summary, index))
        await self.handler(
            None,
            self,
            type(
                "AppliedEvent",
                (),
                {
                    "original_message_count": 4,
                    "new_message_count": 3,
                    "summarized_message_count": 1,
                    "preserved_message_count": 2,
                },
            )(),
        )


class _FakeAssistantAggregator:
    def __init__(self):
        self._summarizer = _FakeSummarizer()

    def add_event_handler(self, _event, handler):
        self._summarizer.handler = handler


async def test_summary_result_waits_for_foreground_response_end_before_applying():
    import copy
    from types import SimpleNamespace

    from voice_runtime.execution.summarization import ContextSummaryCoordinator

    messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "old turn"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "new turn"},
    ]
    tracker = _FakeTracker()
    context = type("Context", (), {"get_messages": lambda _self: messages})()
    coordinator = ContextSummaryCoordinator(
        tracker=tracker,
        context=context,
        config={},
        provider="gemini",
        model="test-model",
        llm=None,
        credential_available=True,
    )
    assistant = _FakeAssistantAggregator()
    coordinator.attach(assistant)
    coordinator.flow = SimpleNamespace(context_generation=2)
    coordinator.observer = SimpleNamespace(llm_operation={"operation_id": "inference"})
    coordinator.pending = {
        "operation": {"operation_id": "summary-op"},
        "operation_id": "summary-op",
        "request_id": "request-1",
        "last_index": 2,
        "prefix": copy.deepcopy(messages[:3]),
        "generation": 2,
        "trigger_reason": "completed_exchange_threshold",
        "source_message_ids": [],
        "generated_at": "now",
    }

    await assistant._summarizer._handle_summary_result(
        SimpleNamespace(
            request_id="request-1",
            error=None,
            last_summarized_index=2,
            summary="Business: confirmed",
        )
    )
    assert assistant._summarizer.applied == []
    assert coordinator.deferred_result is not None

    coordinator.observer.llm_operation = None
    await coordinator.apply_deferred_if_idle()

    assert assistant._summarizer.applied == [("Business: confirmed", 2)]
    assert coordinator.pending is None
    assert tracker.diagnostics[-1]["code"] == "applied"
