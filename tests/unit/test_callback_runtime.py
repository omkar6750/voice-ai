import httpx
from voice_runtime.execution.native import _callback_api_success_result


def test_callback_api_rejection_becomes_explicit_tool_error():
    response = httpx.Response(
        502,
        json={"detail": "Google Calendar availability could not be checked"},
        request=httpx.Request("POST", "http://localhost/callback-scheduling/availability"),
    )

    assert _callback_api_success_result(response) == {
        "status": "error",
        "error": "Google Calendar availability could not be checked",
    }


def test_callback_api_success_requires_json_object():
    response = httpx.Response(
        200,
        json=[{"display": "Tomorrow at 10:00 AM"}],
        request=httpx.Request("POST", "http://localhost/callback-scheduling/availability"),
    )

    assert _callback_api_success_result(response) == {
        "status": "error",
        "error": "Callback API returned an invalid result",
    }
