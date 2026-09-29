"""New customer routes must not silently escape the organization boundary."""

from fastapi.routing import APIRoute, APIWebSocketRoute
from voice_api.api.v1.api import api_router


def routes(router):
    for route in router.routes:
        if hasattr(route, "original_router"):
            yield from routes(route.original_router)
        else:
            yield route


def dependencies(dependant):
    yield getattr(dependant.call, "__name__", "")
    for child in dependant.dependencies:
        yield from dependencies(child)


# These callbacks authenticate vendor signatures/state in their owning services.
# Exact paths and verbs make newly added public endpoints an explicit audit decision.
PUBLIC_CALLBACKS = {
    ("/auth/clerk/webhook", "POST"),
    ("/integrations/whatsapp/{connection_id}/webhook", "GET"),
    ("/integrations/whatsapp/{connection_id}/webhook", "POST"),
    ("/calendar-integrations/google/callback", "GET"),
    ("/telephony/twilio/call-status/{correlation_id}", "POST"),
    ("/telephony/twilio/stream-status/{correlation_id}", "POST"),
}


def test_every_http_route_has_reviewed_authentication_boundary():
    for route in routes(api_router):
        if not isinstance(route, APIRoute):
            continue
        gates = set(dependencies(route.dependant))
        for method in route.methods:
            if (route.path, method) in PUBLIC_CALLBACKS:
                continue
            assert "require_clerk_user" in gates or "require_runtime_service" in gates, (
                method,
                route.path,
                "Missing authentication",
            )
            if route.path in {"/me", "/auth/me"} or route.path.startswith(("/orgs", "/platform")):
                # These catalog routes check actor/path membership and capabilities
                # directly, before binding the target organization.
                continue
            assert gates & {
                "require_organization_access",
                "require_legacy_data_access",
                "require_runtime_service",
            }, (method, route.path, "Missing customer scope boundary")


def test_only_reviewed_websocket_handshakes_are_public():
    assert {route.path for route in routes(api_router) if isinstance(route, APIWebSocketRoute)} == {
        "/browser-sessions/{session_id}/ws",
        "/telephony/twilio/media/{correlation_id}",
    }
