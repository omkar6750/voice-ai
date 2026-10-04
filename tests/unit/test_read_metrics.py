"""Development HTTP metrics are content-free and inactive in production."""

import httpx
import pytest
from fastapi import FastAPI
from voice_api.core.read_metrics import ReadMetricsMiddleware, current, record, timed_read

from voice_runtime import perf_diagnostics


@pytest.mark.asyncio
async def test_diagnostic_headers_and_logs_are_development_only(monkeypatch):
    records = []
    monkeypatch.setattr(
        "voice_api.core.read_metrics.emit", lambda record, **kwargs: records.append(record)
    )
    app = FastAPI()
    app.add_middleware(ReadMetricsMiddleware)

    @app.get("/read")
    @timed_read
    async def read():
        record("db", 5)
        if (metrics := current.get()) is not None:
            metrics.queries = 2
        return {"value": "private response body"}

    try:
        perf_diagnostics.configure(env="dev", enabled=True)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.get("/read", headers={"Authorization": "secret"})
        assert "db;dur=5.00" in response.headers["server-timing"]
        log = records.pop()
        assert log["trace_id"] == response.headers["x-request-id"]
        assert log["query_count"] == 2
        assert log["response_bytes"] == len(response.content)
        assert "private" not in str(log) and "secret" not in str(log)
        perf_diagnostics.configure(env="production", enabled=True)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.get("/read")
        assert "server-timing" not in response.headers
        assert "x-request-id" not in response.headers
        assert not records
    finally:
        perf_diagnostics.configure(env="dev", enabled=False)
