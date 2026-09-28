import httpx
import pytest
from voice_api.services.whatsapp_service import ProviderError, WhatsAppAdapter


@pytest.mark.asyncio
async def test_preview_fetches_only_validated_meta_image_url() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={"url": "https://lookaside.fbsbx.com/media", "mime_type": "image/png"},
            )
        return httpx.Response(200, content=b"image-bytes", headers={"content-type": "image/png"})

    adapter = WhatsAppAdapter(
        "secret-token", "1234", "5678", "v23.0", transport=httpx.MockTransport(handler)
    )
    async with adapter:
        content, mime_type = await adapter.preview_image("9988", max_bytes=100)

    assert content == b"image-bytes"
    assert mime_type == "image/png"
    assert requests[0].url.path.endswith("/9988")
    assert requests[1].url.host == "lookaside.fbsbx.com"
    assert requests[1].headers["authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_preview_rejects_untrusted_provider_url_without_fetching_it() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"url": "https://attacker.example/image", "mime_type": "image/png"},
        )

    adapter = WhatsAppAdapter(
        "secret-token", "1234", "5678", "v23.0", transport=httpx.MockTransport(handler)
    )
    async with adapter:
        with pytest.raises(ProviderError):
            await adapter.preview_image("9988", max_bytes=100)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_preview_enforces_byte_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "graph.facebook.com":
            return httpx.Response(
                200,
                json={"url": "https://lookaside.fbsbx.com/media", "mime_type": "image/jpeg"},
            )
        return httpx.Response(200, content=b"x" * 101, headers={"content-type": "image/jpeg"})

    adapter = WhatsAppAdapter(
        "secret-token", "1234", "5678", "v23.0", transport=httpx.MockTransport(handler)
    )
    async with adapter:
        with pytest.raises(ProviderError):
            await adapter.preview_image("9988", max_bytes=100)


@pytest.mark.asyncio
async def test_delete_treats_provider_absence_as_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["phone_number_id"] == "1234"
        return httpx.Response(404)

    adapter = WhatsAppAdapter(
        "secret-token", "1234", "5678", "v23.0", transport=httpx.MockTransport(handler)
    )
    async with adapter:
        await adapter.delete_media("9988")


@pytest.mark.asyncio
async def test_delete_requires_provider_confirmation() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": False})

    adapter = WhatsAppAdapter(
        "secret-token", "1234", "5678", "v23.0", transport=httpx.MockTransport(handler)
    )
    async with adapter:
        with pytest.raises(ProviderError):
            await adapter.delete_media("9988")
