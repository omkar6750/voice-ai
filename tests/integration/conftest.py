"""Isolated PostgreSQL sessions: all per-test writes roll back."""

import os

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from voice_api.auth import require_operator
from voice_api.db import get_session
from voice_api.main import app


@pytest.fixture
async def database():
    url = os.getenv("VOICE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set isolated VOICE_TEST_DATABASE_URL")
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            outer = await connection.begin()
            try:
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def client(database):
    async def session_override():
        yield database

    async def operator_override():
        return None

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[require_operator] = operator_override
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as value:
            yield value
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
