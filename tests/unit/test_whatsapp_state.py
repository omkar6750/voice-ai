from voice_runtime.execution.whatsapp_state import begin_send, finish_send, record_send_fact


def test_send_fact_requires_confirmed_provider_receipt():
    state = {}
    assert record_send_fact(state, True)["status"] == "error"
    assert begin_send(state, "followup") is None
    assert begin_send(state, "followup")["status"] == "uncertain"
    finish_send(state, "followup", {"status": "ok", "message_id": "wamid.confirmed"})
    assert state["whatsapp_sent"] is True
    assert record_send_fact(state, True)["status"] == "ok"
    assert record_send_fact(state, False)["status"] == "error"
    assert begin_send(state, "followup")["duplicate_prevented"]


def test_uncertain_or_failed_send_is_not_repeated_and_never_claimed_sent():
    for result in [
        {"status": "uncertain"},
        {"status": "error"},
        {"status": "ok", "message_id": "unknown"},
    ]:
        state = {}
        assert begin_send(state, "followup") is None
        finish_send(state, "followup", result)
        assert not state.get("whatsapp_sent")
        assert record_send_fact(state, True)["status"] == "error"
        assert begin_send(state, "followup") is not None


def test_checkpoint_restores_duplicate_guard_and_sessions_are_isolated():
    from copy import deepcopy

    state = {}
    begin_send(state, "followup")
    finish_send(state, "followup", {"status": "ok", "message_id": "receipt"})
    restored = deepcopy(state)
    assert begin_send(restored, "followup")["duplicate_prevented"]
    assert begin_send({}, "followup") is None
