from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from voice_api.services.read_pagination import decode_cursor, encode_cursor


def test_cursor_roundtrip_and_scope_filters_are_not_authorization():
    stamp = datetime.now(UTC)
    cursor = encode_cursor("org-a", {"status": "failed"}, stamp, "run-a")
    assert decode_cursor(cursor, "org-a", {"status": "failed"}) == (stamp, "run-a")
    for org, filters in [("org-b", {"status": "failed"}), ("org-a", {"status": "running"})]:
        with pytest.raises(HTTPException) as error:
            decode_cursor(cursor, org, filters)
        assert error.value.status_code == 422


@pytest.mark.parametrize("cursor", ["!", "a", "W10", "x" * 1025, "bnVsbA"])
def test_malformed_cursors_return_safe_validation_error(cursor):
    with pytest.raises(HTTPException) as error:
        decode_cursor(cursor, "org-a", {})
    assert error.value.detail == "Invalid pagination cursor"
