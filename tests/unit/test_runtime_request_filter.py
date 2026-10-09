from types import SimpleNamespace

import pytest
from voice_shared.http_clients import route_label

from voice_shared import request_evidence


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/runtime/artifacts/grant",
        "/api/v1/runtime/artifacts/abc/def/upload",
        "/api/v1/runtime/artifacts/complete",
        ":id/api/v1/runtime/artifacts/grant",
        "/api/v1/runtime/sync",
    ],
)
def test_internal_transport_is_not_agent_activity(path):
    assert request_evidence.is_internal_span(
        SimpleNamespace(category="http_request", attributes={"endpoint": path})
    )
    events = []
    token = request_evidence.sink.set(events.append)
    try:
        assert request_evidence.begin("POST", path, "voice-runtime") is None
        assert events == []
    finally:
        request_evidence.sink.reset(token)


def test_external_action_and_provider_requests_are_preserved():
    events = []
    token = request_evidence.sink.set(events.append)
    try:
        for path in ("/v1/chat/completions", "/api/v1/contacts", "/api/v1/runtime/tools/execute"):
            assert request_evidence.begin("POST", path, "voice-runtime") is not None
        assert len(events) == 3
    finally:
        request_evidence.sink.reset(token)


def test_route_label_preserves_leading_slash_and_redacts_identifiers():
    assert (
        str(route_label("/api/v1/runtime/artifacts/private/upload"))
        == "/api/v1/runtime/artifacts/:id/upload"
    )
