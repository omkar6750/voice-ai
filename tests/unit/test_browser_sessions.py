"""Unit tests for WebSocket browser test sessions and Dashboard transport provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.main import app
from voice_api.models import Agent, AgentVersion, BrowserSession, Contact, Run
from voice_api.models.common import new_id
from voice_api.services.browser_session_service import (
    BrowserSessionContext,
    BrowserSessionManager,
    create_browser_session,
    end_browser_session,
    issue_browser_ticket,
)


@pytest.mark.asyncio
async def test_create_browser_session_creates_run_and_session():
    session = AsyncMock(spec=AsyncSession)
    version_id = new_id()
    version = AgentVersion(
        id=version_id,
        agent_id=new_id(),
        version=1,
        revision=1,
        status="published",
        config={"flow": {"nodes": []}},
    )

    session.get.return_value = version

    with patch(
        "voice_api.services.browser_session_service.resolve",
        return_value=({"flow": {"nodes": []}}, "hash123"),
    ):
        run, browser_session = await create_browser_session(
            session=session,
            agent_version_id=version_id,
        )

        assert run.channel == "browser"
        assert run.transport_provider == "dashboard"
        assert run.contact_id is None
        assert run.endpoint_id is None
        assert run.status == "claimed"
        assert browser_session.run_id == run.id
        assert browser_session.status == "created"
        assert browser_session.expires_at is not None


@pytest.mark.asyncio
async def test_create_browser_session_rejects_version_from_another_agent():
    session = AsyncMock(spec=AsyncSession)
    version = AgentVersion(
        id="version-a",
        agent_id="agent-a",
        version=1,
        revision=1,
        status="published",
        config={"flow": {"nodes": []}},
    )
    session.get.return_value = version

    with pytest.raises(HTTPException) as exc_info:
        await create_browser_session(
            session=session,
            agent_id="agent-b",
            agent_version_id="version-a",
        )

    assert exc_info.value.status_code == 422
    assert "does not belong" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_browser_session_resolves_version_within_selected_agent():
    session = AsyncMock(spec=AsyncSession)
    agent = Agent(id="agent-a", name="Agent A", active_version_id=None)
    version = AgentVersion(
        id="version-a",
        agent_id="agent-a",
        version=3,
        revision=1,
        status="published",
        config={"flow": {"nodes": []}},
    )

    async def get_mock(model, ident):
        if model is Agent and ident == "agent-a":
            return agent
        return None

    session.get.side_effect = get_mock
    session.scalar.return_value = version

    with patch(
        "voice_api.services.browser_session_service.resolve",
        return_value=({"flow": {"nodes": []}}, "hash123"),
    ):
        run, _ = await create_browser_session(session=session, agent_id="agent-a")

    assert run.agent_version_id == "version-a"


@pytest.mark.asyncio
async def test_create_browser_session_requires_agent_when_version_is_omitted():
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(HTTPException) as exc_info:
        await create_browser_session(session=session)

    assert exc_info.value.status_code == 422
    assert "select an agent" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_create_browser_session_with_contact_and_override_number():
    session = AsyncMock(spec=AsyncSession)
    version_id = new_id()
    contact_id = new_id()
    version = AgentVersion(
        id=version_id,
        agent_id=new_id(),
        version=1,
        revision=1,
        status="published",
        config={"flow": {"nodes": []}},
    )
    contact = Contact(
        id=contact_id,
        name="Omkar Pawar",
        phone_number="+917304058886",
        timezone="Asia/Kolkata",
        business="Tech Corp",
        source="Website",
        language="en",
        metadata_json={"query": "Voice AI Platform"},
    )

    async def get_mock(model, ident):
        if model == AgentVersion:
            return version
        if model == Contact and ident == contact_id:
            return contact
        return None

    session.get.side_effect = get_mock

    with patch(
        "voice_api.services.browser_session_service.resolve",
        return_value=({"flow": {"nodes": []}}, "hash123"),
    ):
        run, browser_session = await create_browser_session(
            session=session,
            agent_version_id=version_id,
            contact_id=contact_id,
            phone_number="+919999988888",
            contact_variables={"extra_note": "priority customer"},
        )

        assert run.channel == "browser"
        assert run.contact_id == contact_id
        assert run.contact_snapshot["name"] == "Omkar Pawar"
        assert run.contact_snapshot["phone_number"] == "+919999988888"
        assert run.contact_snapshot["metadata_json"]["extra_note"] == "priority customer"
        assert run.resolved_config["_resolved"]["contact"]["name"] == "Omkar Pawar"
        assert run.resolved_config["target_snapshot"] == "+919999988888"
        assert run.resolved_config["contact_id"] == contact_id
        assert browser_session.run_id == run.id


@pytest.mark.asyncio
async def test_create_browser_session_with_custom_test_number_and_variables():
    session = AsyncMock(spec=AsyncSession)
    version_id = new_id()
    version = AgentVersion(
        id=version_id,
        agent_id=new_id(),
        version=1,
        revision=1,
        status="published",
        config={"flow": {"nodes": []}},
    )

    session.get.return_value = version

    with patch(
        "voice_api.services.browser_session_service.resolve",
        return_value=({"flow": {"nodes": []}}, "hash123"),
    ):
        run, browser_session = await create_browser_session(
            session=session,
            agent_version_id=version_id,
            phone_number="+919876543210",
            contact_variables={"name": "Custom Lead", "query": "Pricing"},
        )

        assert run.channel == "browser"
        assert run.contact_id is None
        assert run.contact_snapshot["name"] == "Custom Lead"
        assert run.contact_snapshot["phone_number"] == "+919876543210"
        assert run.resolved_config["_resolved"]["contact"]["name"] == "Custom Lead"
        assert run.resolved_config["target_snapshot"] == "+919876543210"
        assert run.resolved_config["contact_id"].startswith("test-contact-")
        assert browser_session.run_id == run.id


@pytest.mark.asyncio
async def test_browser_session_api_create_and_delete():
    session_mock = AsyncMock(spec=AsyncSession)
    run_id = new_id()
    session_id = new_id()

    run = Run(
        id=run_id,
        channel="browser",
        transport_provider="dashboard",
        agent_version_id="av1",
        status="claimed",
        resolved_config={},
    )
    browser_session = BrowserSession(
        id=session_id,
        run_id=run_id,
        status="created",
    )

    async def mock_get_session():
        yield session_mock

    app.dependency_overrides[get_session] = mock_get_session
    app.dependency_overrides[require_legacy_owner] = lambda: None

    try:
        with patch(
            "voice_api.api.v1.endpoints.browser_sessions.create_browser_session",
            return_value=(run, browser_session),
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.post(
                    "/api/v1/browser-sessions",
                    json={"agent_version_id": "av1"},
                    headers={"Authorization": "Bearer test-clerk-session"},
                )
                assert res.status_code == 201
                data = res.json()
                assert data["id"] == session_id
                assert data["run_id"] == run_id
                assert data["status"] == "created"

        with patch(
            "voice_api.api.v1.endpoints.browser_sessions.end_browser_session",
            return_value={"status": "disconnected"},
        ):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                del_res = await client.delete(
                    f"/api/v1/browser-sessions/{session_id}",
                    headers={"Authorization": "Bearer test-clerk-session"},
                )
                assert del_res.status_code == 200
                assert del_res.json()["status"] == "disconnected"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_websocket_ticket_and_duplicate_rejection():
    session_id = new_id()
    run_id = new_id()
    browser_session = BrowserSession(
        id=session_id,
        run_id=run_id,
        status="created",
        org_id="org-test",
    )
    run = Run(
        id=run_id,
        org_id="org-test",
        channel="browser",
        transport_provider="dashboard",
        agent_version_id="av1",
        status="claimed",
        resolved_config={"flow": {"nodes": []}, "audio": {"sample_rate": 16000}},
    )

    session_mock = AsyncMock(spec=AsyncSession)

    async def mock_get(model, pk):
        if model is BrowserSession:
            return browser_session
        if model is Run:
            return run
        return None

    session_mock.get.side_effect = mock_get

    manager = BrowserSessionManager()
    with patch(
        "voice_api.services.browser_session_service.browser_session_manager",
        manager,
    ):
        response = await issue_browser_ticket(session_id, session_mock)
        assert response["ticket"]
        assert await manager.consume_ticket(session_id, "wrong") is None
        ctx = await manager.consume_ticket(session_id, response["ticket"])
        assert ctx is not None
        assert ctx.org_id == "org-test"
        assert await manager.consume_ticket(session_id, response["ticket"]) is None
        with pytest.raises(HTTPException) as exc_info:
            await issue_browser_ticket(session_id, session_mock)
        assert exc_info.value.status_code == 409

        run.org_id = "org-other"
        with pytest.raises(HTTPException) as mismatched:
            await issue_browser_ticket(session_id, session_mock)
        assert mismatched.value.status_code == 404


@pytest.mark.asyncio
async def test_end_browser_session_cleans_up():
    session_id = new_id()
    run_id = new_id()
    browser_session = BrowserSession(
        id=session_id,
        run_id=run_id,
        status="connected",
    )
    run = Run(
        id=run_id,
        channel="browser",
        transport_provider="dashboard",
        status="running",
        resolved_config={},
    )

    session_mock = AsyncMock(spec=AsyncSession)

    async def mock_get(model, pk):
        if model is BrowserSession:
            return browser_session
        if model is Run:
            return run
        return None

    session_mock.get.side_effect = mock_get

    ctx = BrowserSessionContext(session_id, run_id, {}, "org-test")
    ctx.host = AsyncMock()

    manager = BrowserSessionManager()
    manager._sessions[session_id] = ctx

    with patch(
        "voice_api.services.browser_session_service.browser_session_manager",
        manager,
    ):
        res = await end_browser_session(session_id, session_mock)
        assert res["status"] == "disconnected"
        assert not ctx.is_active
        ctx.host.close.assert_awaited_once()
        assert browser_session.status == "disconnected"
        assert run.status == "completed"

        # Repeated cleanup is safe and does not close resources a second time.
        await end_browser_session(session_id, session_mock)
        ctx.host.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_runs_list_normalizes_transport_provider():
    session_mock = AsyncMock(spec=AsyncSession)
    run_browser = Run(
        id="run-b1",
        channel="browser",
        transport_provider="dashboard",
        status="completed",
        agent_version_id="av1",
        resolved_config={},
        contact_snapshot={},
    )
    run_sim = Run(
        id="run-s1",
        channel="phone",
        transport_provider="sim7600",
        status="completed",
        agent_version_id="av1",
        resolved_config={},
        contact_snapshot={},
    )
    run_twilio = Run(
        id="run-t1",
        channel="phone",
        transport_provider="twilio",
        status="completed",
        agent_version_id="av1",
        resolved_config={},
        contact_snapshot={},
    )

    async def mock_scalars(query):
        mock_result = MagicMock()
        query_str = str(query).lower()
        if "calls" in query_str:
            mock_result.all.return_value = []
        else:
            mock_result.all.return_value = [run_browser, run_sim, run_twilio]
        return mock_result

    session_mock.scalars = AsyncMock(side_effect=mock_scalars)

    async def mock_get_session():
        yield session_mock

    app.dependency_overrides[get_session] = mock_get_session
    app.dependency_overrides[require_legacy_owner] = lambda: None

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(
                "/api/v1/runs",
                headers={"Authorization": "Bearer test-clerk-session"},
            )
            assert res.status_code == 200
            runs = res.json()["runs"]
            assert len(runs) == 3
            assert runs[0]["transport_provider"] == "dashboard"
            assert runs[1]["transport_provider"] == "sim7600"
            assert runs[2]["transport_provider"] == "twilio"
    finally:
        app.dependency_overrides.clear()
