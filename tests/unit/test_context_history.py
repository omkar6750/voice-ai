from voice_runtime.execution.context import ContextHistory


def test_summary_preserves_newer_messages_and_rejects_stale_prefix():
    history = ContextHistory()
    for i in range(6):
        history.append(str(i), {"role": "user", "content": str(i)})
    captured = history.capture_prefix(1, 2)
    history.append("new", {"role": "user", "content": "new"})
    assert history.apply_summary(captured, "summary", "Captured messages only")
    assert [m.id for m in history.messages] == ["0", "summary", "4", "5", "new"]
    assert not history.apply_summary(captured, "stale", "Outdated")


def test_compaction_never_orphans_tool_results():
    history = ContextHistory()
    history.append("call", {"role": "assistant", "tool_calls": [{"id": "tool-1"}]})
    history.append("result", {"role": "tool", "tool_call_id": "tool-1", "content": "done"})
    assert history.capture_prefix(0, 1) == ()
    assert history.capture_prefix(0, 0) == ("call", "result")
