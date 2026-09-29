"""Local recording protocol; Cloudinary SDK and signed URLs stay in this adapter."""

import asyncio
import hashlib
import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
from fastapi import HTTPException


@dataclass(frozen=True)
class StoredRecording:
    public_id: str
    asset_id: str
    version: int
    format: str
    size_bytes: int


class RecordingStorage(Protocol):
    async def upload(
        self, path: Path, public_id: str, checksum: str, size: int
    ) -> StoredRecording: ...
    async def read(self, public_id: str, format: str) -> bytes: ...
    async def delete(self, asset_ids: list[str]) -> dict[str, bool]: ...
    async def resolve(self, public_id: str, checksum: str, size: int) -> StoredRecording | None: ...


def recording_identity(org_id: str, run_id: str, artifact_id: str) -> str:
    # Opaque DB IDs cannot inject vendor path segments, prefixes or transformations.
    identity = hashlib.sha256(f"{org_id}\0{run_id}\0{artifact_id}".encode()).hexdigest()
    return f"voice-recordings/{identity}"


class CloudinaryRecordingStorage:
    def __init__(self, cloud_name: str, api_key: str, api_secret: str, max_bytes: int):
        self.options = dict(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret)
        self.max_bytes = max_bytes

    @staticmethod
    def validate(result: dict, public_id: str, checksum: str, size: int) -> StoredRecording:
        if (
            result.get("public_id") != public_id
            or result.get("resource_type") != "video"
            or result.get("type") != "authenticated"
            or result.get("bytes") != size
            or result.get("context", {}).get("custom", {}).get("sha256") != checksum
            or result.get("format") != "wav"
        ):
            raise ValueError("Stored recording metadata conflict")
        return StoredRecording(
            public_id, result["asset_id"], result["version"], result["format"], size
        )

    async def resolve(self, public_id: str, checksum: str, size: int) -> StoredRecording | None:
        def lookup():
            import cloudinary.api
            import cloudinary.exceptions

            try:
                result = cloudinary.api.resource(
                    public_id, resource_type="video", type="authenticated", **self.options
                )
            except cloudinary.exceptions.NotFound:
                return None
            return self.validate(result, public_id, checksum, size)

        return await asyncio.to_thread(lookup)

    async def upload(self, path: Path, public_id: str, checksum: str, size: int) -> StoredRecording:
        def send():
            import cloudinary.api
            import cloudinary.exceptions
            import cloudinary.uploader

            # Read once: the bytes validated are the bytes sent, even if local storage changes.
            with path.open("rb") as stream:
                data = stream.read(self.max_bytes + 1)
            if (
                len(data) != size
                or size > self.max_bytes
                or hashlib.sha256(data).hexdigest() != checksum
            ):
                raise ValueError("Recording size or checksum changed")
            options = dict(self.options, resource_type="video", type="authenticated")
            try:
                result = cloudinary.api.resource(public_id, **options)
            except cloudinary.exceptions.NotFound:
                result = cloudinary.uploader.upload(
                    io.BytesIO(data),
                    public_id=public_id,
                    overwrite=False,
                    unique_filename=False,
                    context={"sha256": checksum},
                    **options,
                )
                # Query persisted metadata on every replay, including uncertain uploads.
                result = cloudinary.api.resource(public_id, **options)
            return self.validate(result, public_id, checksum, size)

        return await asyncio.to_thread(send)

    async def read(self, public_id: str, format: str) -> bytes:
        import cloudinary.utils

        url = cloudinary.utils.private_download_url(
            public_id,
            format,
            resource_type="video",
            type="authenticated",
            expires_at=int(time.time()) + 60,
            **self.options,
        )
        async with httpx.AsyncClient(timeout=60, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                parts, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise ValueError("Stored recording exceeds size limit")
                    parts.append(chunk)
                return b"".join(parts)

    async def delete(self, asset_ids: list[str]) -> dict[str, bool]:
        if not asset_ids or len(asset_ids) > 100:
            raise ValueError("Deletion requires 1-100 trusted identities")

        def remove():
            import cloudinary.api
            import cloudinary.exceptions

            cloudinary.api.delete_resources_by_asset_ids(
                asset_ids,
                keep_original=False,
                invalidate=True,
                **self.options,
            )
            # Official sample uses public IDs as `deleted` keys even for asset-ID
            # deletion, and the Python SDK returns JSON unchanged. Never assume those
            # keys are asset IDs. Confirm absence by each immutable requested asset ID.
            confirmed = {}
            for asset_id in asset_ids:
                try:
                    cloudinary.api.resource_by_asset_id(asset_id, **self.options)
                except cloudinary.exceptions.NotFound:
                    confirmed[asset_id] = True
                else:
                    confirmed[asset_id] = False
            return confirmed

        return await asyncio.to_thread(remove)


def get_recording_storage() -> RecordingStorage:
    from voice_api.core.config import get_settings

    settings = get_settings()
    values = [
        getattr(settings, f"cloudinary_{name}", None)
        for name in ("cloud_name", "api_key", "api_secret")
    ]
    values = [
        value.get_secret_value() if hasattr(value, "get_secret_value") else value
        for value in values
    ]
    if not all(values):
        raise HTTPException(503, "Recording storage is not configured")
    return CloudinaryRecordingStorage(
        *values, getattr(settings, "recording_max_bytes", 100_000_000)
    )


def recording_admission(
    *, required: bool, configured: bool, used_bytes: int | None, quota_bytes: int | None
) -> dict:
    """Caller must supply current platform quota telemetry; no vendor call or worker."""
    exhausted = quota_bytes is not None and used_bytes is not None and used_bytes >= quota_bytes
    warning = (
        "Recording storage unavailable"
        if not configured
        else "Recording quota exhausted"
        if exhausted
        else "Recording quota above 80%"
        if quota_bytes and used_bytes is not None and used_bytes >= quota_bytes * 0.8
        else None
    )
    if required and (not configured or exhausted or used_bytes is None or quota_bytes is None):
        raise HTTPException(
            503, "Recording-required call cannot be admitted: storage capacity unavailable"
        )
    return {"warning": warning, "used_bytes": used_bytes, "quota_bytes": quota_bytes}
