import httpx
import pytest
from voice_api.core.config import Settings
from voice_api.main import app


@pytest.mark.asyncio
async def test_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voice-api"}


@pytest.mark.asyncio
async def test_providers_and_config_schema_routes(monkeypatch) -> None:
    monkeypatch.setattr(
        "voice_api.core.security.get_settings", lambda: Settings(operator_token="test-token")
    )
    monkeypatch.setattr(
        "voice_api.api.deps.get_settings", lambda: Settings(operator_token="test-token")
    )
    headers = {"Authorization": "Bearer test-token"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test backward-compatible /api prefix
        res1 = await client.get("/api/providers", headers=headers)
        assert res1.status_code == 200
        assert "providers" in res1.json()

        # Test standardized /api/v1 prefix
        res2 = await client.get("/api/v1/providers", headers=headers)
        assert res2.status_code == 200
        assert res2.json() == res1.json()

        # Test config-schema routes
        res_schema1 = await client.get("/api/config-schema", headers=headers)
        res_schema2 = await client.get("/api/v1/config-schema", headers=headers)
        assert res_schema1.status_code == 200
        assert res_schema2.status_code == 200
        assert "agent" in res_schema1.json()
