"""Confirmed WhatsApp facts and one-attempt follow-ups within a conversation."""

_CACHE = "_whatsapp_send_outcomes"


def begin_send(state: dict, binding_key: str) -> dict | None:
    outcomes = state.setdefault(_CACHE, {})
    if binding_key in outcomes:
        return {**outcomes[binding_key], "duplicate_prevented": True}
    outcomes[binding_key] = {
        "status": "uncertain",
        "error": "A WhatsApp send is already in progress or its result is unknown. Do not resend.",
    }
    return None


def finish_send(state: dict, binding_key: str, result: dict) -> None:
    receipt = result.get("message_id")
    confirmed = result.get("status") == "ok" and receipt not in (None, "", "unknown")
    state[_CACHE][binding_key] = dict(result)
    if confirmed:
        state["whatsapp_sent"] = True
    elif result.get("status") == "ok":
        state[_CACHE][binding_key] = {
            "status": "uncertain",
            "error": "Provider accepted the request but supplied no verifiable message ID. Do not resend.",
        }


def record_send_fact(state: dict, value) -> dict:
    confirmed = any(
        r.get("status") == "ok" and r.get("message_id") not in (None, "", "unknown")
        for r in state.get(_CACHE, {}).values()
    )
    if value is not True or not confirmed:
        return {
            "status": "error",
            "error": "whatsapp_sent is derived from a confirmed provider message ID and cannot be asserted or reset by the model.",
        }
    state["whatsapp_sent"] = True
    return {"status": "ok", "key": "whatsapp_sent", "value": True}
