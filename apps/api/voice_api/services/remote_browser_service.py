"""Browser configuration lives in API; media and pipelines live in runtime."""

from datetime import timedelta
from typing import Any

from fastapi import HTTPException, WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voice_api.core.hosting import require_hosted_call_admission
from voice_api.models import Agent, AgentVersion, BrowserSession, Contact, Run
from voice_api.models.common import new_id, now
from voice_api.services.resolution_service import fingerprint, resolve
from voice_api.services.runtime_dispatch import control, dispatch, identity, stop


async def create_browser_session(
    session: AsyncSession,
    agent_id: str | None = None,
    agent_version_id: str | None = None,
    contact_id: str | None = None,
    phone_number: str | None = None,
    contact_variables: dict[str, Any] | None = None,
    logging_override: bool | None = None,
) -> tuple[Run, BrowserSession]:
    """Create a Run and associated BrowserSession for in-browser testing."""
    require_hosted_call_admission("browser")
    if agent_version_id:
        version = await session.get(AgentVersion, agent_version_id)
        if version is None:
            raise HTTPException(404, "Agent version not found")
        if agent_id and version.agent_id != agent_id:
            raise HTTPException(422, "Agent version does not belong to the selected agent")
    else:
        if not agent_id:
            raise HTTPException(422, "Select an agent before starting a browser test")
        agent = await session.get(Agent, agent_id)
        if agent is None:
            raise HTTPException(404, "Agent not found")
        version = None
        if agent.active_version_id:
            active = await session.get(AgentVersion, agent.active_version_id)
            if active is not None and active.status == "published":
                version = active
        if version is None:
            version = await session.scalar(
                select(AgentVersion)
                .where(
                    AgentVersion.agent_id == agent_id,
                    AgentVersion.status == "published",
                )
                .order_by(AgentVersion.version.desc())
            )
        if version is None:
            raise HTTPException(422, "Selected agent has no published version to test")

    resolved_contact_id: str | None = None
    contact_snapshot: dict[str, Any] = {}

    if contact_id:
        contact = await session.get(Contact, contact_id)
        if contact is None:
            raise HTTPException(404, "Contact not found")
        resolved_contact_id = contact.id
        effective_phone = (
            phone_number.strip() if phone_number and phone_number.strip() else contact.phone_number
        )
        contact_snapshot = {
            "id": contact.id,
            "name": contact.name,
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "timezone": contact.timezone or "UTC",
            "phone_number": effective_phone,
            "business": contact.business,
            "source": contact.source,
            "language": contact.language or "en",
            "metadata_json": dict(contact.metadata_json or {}),
        }
        if contact_variables:
            for k, v in contact_variables.items():
                contact_snapshot["metadata_json"][k] = v
                if k in ("name", "business", "source", "timezone", "language") and v:
                    contact_snapshot[k] = v
    elif (phone_number and phone_number.strip()) or contact_variables:
        clean_phone = (phone_number or "").strip()
        custom_vars = dict(contact_variables or {})
        synth_name = custom_vars.get("name") or "Test Caller"
        synth_id = f"test-contact-{new_id()[:8]}"
        contact_snapshot = {
            "id": synth_id,
            "name": synth_name,
            "timezone": custom_vars.get("timezone", "UTC"),
            "phone_number": clean_phone,
            "business": custom_vars.get("business"),
            "source": custom_vars.get("source", "browser_test"),
            "language": custom_vars.get("language", "en"),
            "metadata_json": custom_vars,
        }

    config, digest = await resolve(session, version, logging_override)

    snapshot = dict(config)
    resolved_dict = dict(snapshot.get("_resolved", {}))
    if contact_snapshot:
        resolved_dict["contact"] = contact_snapshot
        snapshot["contact_snapshot"] = contact_snapshot
        snapshot["target_snapshot"] = contact_snapshot.get("phone_number", "")
        snapshot["contact_id"] = resolved_contact_id or contact_snapshot.get("id")
    snapshot["agent_version_id"] = version.id
    snapshot["_resolved"] = resolved_dict
    digest = fingerprint(snapshot)

    run = Run(
        id=new_id(),
        channel="browser",
        transport_provider="dashboard",
        agent_version_id=version.id,
        contact_id=resolved_contact_id,
        endpoint_id=None,
        # Dispatch compiles the snapshot before claiming and freezing it.
        status="queued",
        resolved_config=snapshot,
        config_hash=digest,
        snapshot_schema_version=1,
        contact_snapshot=contact_snapshot,
    )
    session.add(run)
    await session.flush()

    browser_session = BrowserSession(
        id=new_id(),
        run_id=run.id,
        status="created",
        expires_at=now() + timedelta(minutes=5),
    )
    session.add(browser_session)
    await session.commit()

    return run, browser_session


async def issue_browser_ticket(
    session_id: str, session: AsyncSession, *, actor_user_id: str | None = None
) -> dict:
    require_hosted_call_admission("browser")
    if not actor_user_id:
        raise HTTPException(403, "Authenticated browser actor required")
    browser = await session.get(BrowserSession, session_id)
    if not browser or browser.status != "created" or browser.expires_at <= now():
        raise HTTPException(410, "Browser session unavailable")
    run = await session.get(Run, browser.run_id)
    if not run or run.org_id != browser.org_id:
        raise HTTPException(404, "Browser run unavailable")
    assignment = await dispatch(session, run, browser_session_id=session_id)
    return await control("/v1/sessions/browser-ticket", identity(assignment))


async def end_browser_session(
    session_id: str, session: AsyncSession, *, reason: str = "operator_stop"
) -> dict:
    browser = await session.get(BrowserSession, session_id)
    if not browser:
        raise HTTPException(404, "Browser session not found")
    await stop(session, browser.run_id)
    return {"status": "stopping", "session_id": session_id}


async def handle_browser_socket(session_id: str, websocket: WebSocket, settings) -> None:
    await websocket.close(code=1008)
