from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile
from voice_api.api.v1.endpoints import integrations
from voice_api.models.common import now


class _FakeSession:
    def __init__(self, connection):
        self.connection = connection
        self.row = None
        self.commit = AsyncMock(side_effect=self._commit)

    async def get(self, _model, _id):
        return self.connection

    def add(self, row):
        self.row = row

    async def _commit(self):
        self.row.uploaded_at = now()


class _FakeAdapter:
    def __init__(self):
        self.uploaded = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def upload_media(self, filename, mime_type, content):
        self.uploaded = (filename, mime_type, content)
        return {"id": "123456"}


def _connection():
    return SimpleNamespace(
        id="connection-1",
        provider="whatsapp",
        enabled=True,
        config={"phone_number_id": "123", "waba_id": "456", "api_version": "v23.0"},
    )


@pytest.mark.asyncio
async def test_upload_sends_png_to_meta_and_persists_no_local_path(monkeypatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(integrations, "whatsapp", AsyncMock(return_value=adapter))
    monkeypatch.setattr(
        Path,
        "write_bytes",
        lambda *_args, **_kwargs: pytest.fail("WhatsApp upload wrote image bytes locally"),
    )
    session = _FakeSession(_connection())
    content = b"\x89PNG\r\n\x1a\nencoded-image-payload"
    upload = UploadFile(
        file=BytesIO(content), filename="catalog.png", headers={"content-type": "image/png"}
    )

    response = await integrations.upload_media(
        "connection-1", upload, display_name="Catalog", session=session, _=None
    )

    assert response.provider_media_id == "123456"
    assert adapter.uploaded == ("catalog.png", "image/png", content)
    assert session.row.provider_media_id == "123456"
    assert not hasattr(session.row, "source_path")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "mime_type"),
    [
        (b"not an image", "image/png"),
        (b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024), "image/png"),
        (b"GIF89a", "image/gif"),
    ],
    ids=("bad-signature", "oversized", "gif"),
)
async def test_upload_rejects_invalid_or_oversized_image(content, mime_type, monkeypatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(integrations, "whatsapp", AsyncMock(return_value=adapter))
    upload = UploadFile(
        file=BytesIO(content),
        filename="image.bin",
        headers={"content-type": mime_type},
    )
    with pytest.raises(HTTPException) as error:
        await integrations.upload_media(
            "connection-1", upload, session=_FakeSession(_connection()), _=None
        )
    assert error.value.status_code == 422
    assert adapter.uploaded is None
