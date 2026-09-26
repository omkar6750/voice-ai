from urllib.parse import parse_qs, urlparse

from voice_api.services.calendar_service import google_flow


def test_google_authorization_url_contains_pkce_challenge_without_verifier():
    verifier = "v" * 64
    flow = google_flow("state-a", code_verifier=verifier)
    url, returned_state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    query = parse_qs(urlparse(url).query)
    assert returned_state == "state-a"
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"]
    assert "code_verifier" not in query
    assert verifier not in url


def test_concurrent_flows_have_distinct_pkce_challenges():
    first = google_flow("state-a", code_verifier="a" * 64).authorization_url()[0]
    second = google_flow("state-b", code_verifier="b" * 64).authorization_url()[0]
    first_query = parse_qs(urlparse(first).query)
    second_query = parse_qs(urlparse(second).query)
    assert first_query["code_challenge"] != second_query["code_challenge"]
