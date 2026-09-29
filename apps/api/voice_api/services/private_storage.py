"""Server-only private Supabase objects; no signed/public URL crosses the API."""

import hashlib
import json
import re
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import HTTPException
from voice_runtime.safe_logs import RuntimeEvent, safe_event_payload

from voice_api.core.config import get_settings

MAX_PRIVATE_BYTES = 20_000_000


class PrivateStorage(Protocol):
    async def upload(self, key: str, data: bytes) -> None: ...
    async def read(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...


def object_identity(org_id: str, record_id: str, kind: str, checksum: str) -> str:
    if kind not in {"documents", "diagnostics"} or not re.fullmatch(r"[a-f0-9]{64}", checksum):
        raise ValueError("Invalid private object identity")
    return f"{UUID(org_id).hex}/{kind}/{UUID(record_id).hex}/{checksum}"


def check_identity(key: str, org_id: str, record_id: str, kind: str) -> None:
    if key != object_identity(org_id, record_id, kind, key.rsplit("/", 1)[-1]):
        raise ValueError("Private object does not belong to resource")


def sanitized_diagnostics(data: bytes) -> bytes:
    """Reconstruct from the event allowlist, not a blacklist of secret patterns."""
    if len(data) > MAX_PRIVATE_BYTES:
        raise ValueError("Diagnostic artifact too large")
    lines = []
    for line in data.decode("utf-8").splitlines():
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError("Not an operational event")
            event = payload.pop("event", None)
            try:
                event = RuntimeEvent(event)
            except (ValueError, TypeError):
                pass
            safe = safe_event_payload(event, **payload)
        except (ValueError, TypeError):
            safe = {"event": "untrusted_log"}
        lines.append(json.dumps(safe, separators=(",", ":")))
    return ("\n".join(lines) + "\n").encode()


class SupabasePrivateStorage:
    def __init__(self, url: str, service_key: str, bucket: str):
        origin = urlsplit(url)
        if origin.scheme != "https" or not origin.netloc or origin.path not in {"", "/"}:
            raise ValueError("Private storage requires an HTTPS origin")
        if origin.username or origin.password or origin.query or origin.fragment:
            raise ValueError("Invalid private storage origin")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", bucket):
            raise ValueError("Invalid private storage bucket")
        self.base = url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}

    async def _private_bucket(self, client: httpx.AsyncClient) -> None:
        result = await client.get(f"{self.base}/bucket/{self.bucket}", headers=self.headers)
        result.raise_for_status()
        bucket = result.json()
        if bucket.get("id") != self.bucket or bucket.get("public") is not False:
            raise ValueError("Storage bucket must be private")

    def _key(self, key: str) -> str:
        if not re.fullmatch(
            r"[a-f0-9]{32}/(?:documents|diagnostics)/[a-f0-9]{32}/[a-f0-9]{64}", key
        ):
            raise ValueError("Invalid object identity")
        return f"{self.base}/object/{self.bucket}/{key}"

    async def upload(self, key: str, data: bytes) -> None:
        if (
            not data
            or len(data) > MAX_PRIVATE_BYTES
            or hashlib.sha256(data).hexdigest() != key.rsplit("/", 1)[-1]
        ):
            raise ValueError("Private object integrity failure")
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            await self._private_bucket(client)
            response = await client.post(
                self._key(key),
                content=data,
                headers={
                    **self.headers,
                    "Content-Type": "application/octet-stream",
                    "x-upsert": "false",
                },
            )
            if response.status_code in {400, 409}:
                # Replay must confirm exact bytes, never overwrite another object.
                previous = await self.read(key)
                if previous == data:
                    return
                raise ValueError("Private object identity conflict")
            response.raise_for_status()

    async def read(self, key: str) -> bytes:
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            await self._private_bucket(client)
            parts, size = [], 0
            async with client.stream("GET", self._key(key), headers=self.headers) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_PRIVATE_BYTES:
                        raise ValueError("Private object too large")
                    parts.append(chunk)
            data = b"".join(parts)
            if hashlib.sha256(data).hexdigest() != key.rsplit("/", 1)[-1]:
                raise ValueError("Private object integrity failure")
            return data

    async def delete(self, key: str) -> None:
        self._key(key)
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            await self._private_bucket(client)
            response = await client.request(
                "DELETE",
                f"{self.base}/object/{self.bucket}",
                headers=self.headers,
                json={"prefixes": [key]},
            )
            if response.status_code == 404:
                return  # Idempotent retry for an already-removed private object.
            response.raise_for_status()


def get_private_storage() -> PrivateStorage:
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_service_key:
        raise HTTPException(503, "Private document/diagnostic storage is not configured")
    try:
        return SupabasePrivateStorage(
            settings.supabase_url,
            settings.supabase_service_key.get_secret_value(),
            settings.supabase_private_bucket,
        )
    except ValueError:
        raise HTTPException(503, "Private storage configuration is invalid") from None
