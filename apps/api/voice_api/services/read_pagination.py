"""Opaque, scoped cursors for bounded read APIs."""

import base64
import hashlib
import json
from datetime import datetime

from fastapi import HTTPException


def fingerprint(scope: str, filters: dict) -> str:
    return hashlib.sha256(json.dumps([scope, filters], sort_keys=True).encode()).hexdigest()


def encode_cursor(scope: str, filters: dict, created_at: datetime, identity: str) -> str:
    return (
        base64.urlsafe_b64encode(
            json.dumps([fingerprint(scope, filters), created_at.isoformat(), identity]).encode()
        )
        .decode()
        .rstrip("=")
    )


def decode_cursor(cursor: str, scope: str, filters: dict) -> tuple[datetime, str]:
    try:
        if len(cursor) > 1024:
            raise ValueError
        digest, date, identity = json.loads(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        )
        created_at = datetime.fromisoformat(date)
        if (
            digest != fingerprint(scope, filters)
            or not isinstance(identity, str)
            or not created_at.tzinfo
        ):
            raise ValueError
        return created_at, identity
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise HTTPException(422, "Invalid pagination cursor") from exc
