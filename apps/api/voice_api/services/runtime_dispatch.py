"""Dispatch immutable prepared sessions; audio never executes in the API."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from voice_shared.contracts import configuration_hash

from voice_api.core.runtime_config import get_runtime_settings as get_settings
from voice_api.models import Call, Run, RuntimeAssignment
from voice_api.models.common import now
from voice_api.services.provider_credentials import settings_for_snapshot

_client = None


def client():
    global _client
    settings = get_settings()
    if not settings.runtime_control_token:
        raise HTTPException(503, "Runtime control token is not configured")
    if settings.env.casefold() not in {
        "dev",
        "development",
        "local",
    } and not settings.runtime_base_url.startswith("https://"):
        raise HTTPException(503, "Hosted runtime control requires HTTPS")
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.runtime_base_url,
            timeout=20,
            headers={"X-Voice-Runtime-Control-Token": settings.runtime_control_token},
        )
    return _client


async def close_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def control(path, body):
    try:
        response = await client().post(path, json=body)
    except httpx.HTTPError:
        raise HTTPException(503, "Runtime unavailable; check execution before retrying") from None
    if response.status_code >= 400:
        raise HTTPException(
            response.status_code if response.status_code in {404, 409, 422, 503} else 502,
            "Runtime rejected this operation",
        )
    return response.json()


def identity(assignment):
    return {
        "run_id": assignment.run_id,
        "generation": assignment.generation,
        "boot_id": assignment.boot_id,
    }


async def dispatch(session, run, *, browser_session_id="", conversation_id=None, checkpoint=None):
    settings = get_settings()
    run = await session.get(Run, run.id, with_for_update=True, populate_existing=True)
    assignment = await session.get(RuntimeAssignment, run.id)
    if assignment:
        if assignment.state not in {"prepared", "starting", "active"}:
            raise HTTPException(
                409, "Previous runtime attempt requires reconciliation; refusing redial"
            )
        return assignment
    if run.status != "queued":
        raise HTTPException(
            409, "Run is already claimed or ended; refusing to modify its frozen snapshot"
        )
    call = await session.scalar(select(Call).where(Call.run_id == run.id))
    provider = run.channel if run.channel in {"browser", "text_test"} else call.provider
    if provider not in {"browser", "text_test"}:
        if run.status != "queued" or call.status != "queued":
            raise HTTPException(409, "Call is not eligible for a new dispatch")
        from copy import deepcopy

        from voice_api.models import RuntimeEndpoint
        from voice_api.schemas.execution import EndpointConfig

        snapshot = deepcopy(run.resolved_config)
        snapshot["_resolved"]["contact"] = run.contact_snapshot
        snapshot["target_snapshot"] = call.target_snapshot
        snapshot["contact_id"] = run.contact_id
        snapshot["agent_version_id"] = run.agent_version_id
        if provider == "sim7600":
            endpoint = await session.get(RuntimeEndpoint, run.endpoint_id, with_for_update=True)
            if not endpoint:
                raise HTTPException(422, "Dispatch needs an available modem endpoint")
            config = EndpointConfig.model_validate(endpoint.config)
            if snapshot["audio"]["sample_rate"] not in config.sample_rates:
                raise HTTPException(422, "Agent PCM rate is unsupported by endpoint")
            snapshot["_resolved"]["endpoint"] = config.model_dump(mode="json")
        run.resolved_config = snapshot
        run.config_hash = configuration_hash(snapshot)
    from voice_shared.compiler import compile_flow_json

    run.resolved_config = {
        **run.resolved_config,
        "_compiled_flow": compile_flow_json(run.resolved_config),
    }
    run.config_hash = configuration_hash(run.resolved_config)
    resolved = await settings_for_snapshot(
        session, run.org_id, run.resolved_config, settings, run_id=run.id, acquire_slot=False
    )
    credentials = {
        k: v for k, v in (resolved.provider_stage_keys or {}).items() if k != "embedding"
    }
    telephony = {}
    if provider == "twilio":
        from dataclasses import asdict

        from voice_api.services.twilio_service import resolve_twilio_credentials

        _, values = await resolve_twilio_credentials(
            session, call.telephony_connection_id, run_id=run.id
        )
        telephony = {k: v for k, v in asdict(values).items() if v is not None}
        if not values.api_key_sid or not values.api_key_secret:
            raise HTTPException(422, "Twilio REST credentials required")
    # Resolver commits credential leases, so re-lock and re-check ownership before assignment.
    run = await session.get(Run, run.id, with_for_update=True, populate_existing=True)
    if await session.get(RuntimeAssignment, run.id):
        raise HTTPException(409, "Concurrent dispatch already assigned")
    if run.status != "queued":
        raise HTTPException(409, "Run was cancelled before runtime preparation")
    grant = token_urlsafe(32)
    generation = str(uuid4())
    assignment = RuntimeAssignment(
        run_id=run.id,
        org_id=run.org_id,
        generation=generation,
        boot_id=None,
        grant_hash=sha256(grant.encode()).hexdigest(),
        expires_at=now() + timedelta(seconds=900),
        lease_expires_at=now() + timedelta(seconds=30),
        state="preparing",
        metrics={},
        diagnostic_sequence=0,
    )
    session.add(assignment)
    await session.commit()
    body = {
        "version": 1,
        "run_id": run.id,
        "organization_id": run.org_id,
        "generation": generation,
        "grant": grant,
        "expires_at": assignment.expires_at.timestamp(),
        "channel": provider,
        "config_hash": configuration_hash(run.resolved_config),
        "snapshot": run.resolved_config,
        "credentials": credentials,
        "telephony_credentials": telephony,
        "destination": call.target_snapshot if call else "",
        "from_number": (call.from_number or "") if call else "",
        "correlation_id": (call.correlation_id or "") if call else "",
        "browser_session_id": browser_session_id,
        "conversation_id": conversation_id,
        "checkpoint": checkpoint,
        "api_public_base_url": settings.public_base_url or "",
    }
    try:
        prepared = await control("/v1/sessions", body)
    except HTTPException as exc:
        assignment.state = "rejected" if exc.status_code in {409, 422} else "uncertain"
        await session.commit()
        raise
    finally:
        credentials.clear()
        telephony.clear()
        resolved = None
        body.clear()
    assignment = await session.get(
        RuntimeAssignment, run.id, with_for_update=True, populate_existing=True
    )
    assignment.boot_id = prepared["boot_id"]
    if assignment.state == "stopping":
        await session.commit()
        await control("/v1/sessions/stop", identity(assignment))
        return assignment
    assignment.state = "starting"
    if call:
        call.provider_metadata = {
            **(call.provider_metadata or {}),
            "runtime_dispatch_attempted": True,
            "runtime_generation": generation,
        }
        call.status = "dialing"
    if run.status == "queued":
        run.status = "claimed"
    run.claim_token = generation
    run.claimed_at = now()
    run.lease_expires_at = assignment.lease_expires_at
    await session.commit()
    try:
        result = await control("/v1/sessions/start", identity(assignment))
    except HTTPException:
        assignment.state = "uncertain"
        await session.commit()
        raise
    assignment = await session.get(
        RuntimeAssignment, run.id, with_for_update=True, populate_existing=True
    )
    if assignment.state == "starting":
        assignment.state = "active"
    if call and result.get("provider_call_id"):
        call.provider_call_id = result["provider_call_id"]
    await session.commit()
    return assignment


async def stop(session, run_id):
    assignment = await session.get(RuntimeAssignment, run_id, with_for_update=True)
    if not assignment:
        return
    assignment.state = "stopping"
    await session.commit()
    # Preparation may still be in flight. Dispatch observes this fence before starting.
    if assignment.boot_id:
        await control("/v1/sessions/stop", identity(assignment))
