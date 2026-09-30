"""Bounded server-side grants checked throughout the existing runtime wrappers."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from voice_api.core.config import MAX_CALL_DURATION_SECONDS
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_run_organization
from voice_api.models import CallAdmission, CredentialLease, ProviderCredential, Run
from voice_api.models.common import new_id, now

HANDSHAKE_SECONDS = 60
CALL_SECONDS = MAX_CALL_DURATION_SECONDS
CLEANUP_SECONDS = 60
LEASE_SECONDS = HANDSHAKE_SECONDS + CALL_SECONDS + CLEANUP_SECONDS


class CredentialRevoked(ValueError):
    def __init__(self):
        super().__init__("Run credentials expired or were revoked")


def admit_settings(settings) -> None:
    from fastapi import HTTPException

    if getattr(settings, "env", "dev") != "dev" and not getattr(
        settings, "hosted_calls_enabled", False
    ):
        raise HTTPException(503, "Hosted calls are disabled pending runtime acceptance")


def call_seconds(settings, snapshot: dict) -> int:
    return min(
        CALL_SECONDS,
        int(getattr(settings, "call_max_duration_seconds", CALL_SECONDS)),
        int(snapshot.get("call_limits", {}).get("max_duration_secs", CALL_SECONDS)),
    )


async def acquire(session, run_id: str) -> None:
    from fastapi import HTTPException

    slot = await session.get(CallAdmission, 1, with_for_update=True)
    if slot is None:
        raise HTTPException(503, "Runtime admission is unavailable")
    if slot.run_id == run_id:
        if slot.expires_at is None or slot.expires_at <= now():
            raise CredentialRevoked()
        return
    if slot.run_id and slot.expires_at and slot.expires_at > now():
        raise HTTPException(409, "Another call holds the global runtime slot")
    slot.run_id, slot.expires_at = run_id, now() + timedelta(seconds=LEASE_SECONDS)


async def issue(session, run_id: str, credential: ProviderCredential) -> CredentialLease:
    # Credential parent is locked by the resolver, serializing replacement and issuance.
    run = await session.get(Run, run_id)
    if (
        run is None
        or run.org_id != credential.org_id
        or run.status not in {"queued", "claimed", "running"}
    ):
        raise CredentialRevoked()
    lease = await session.scalar(
        select(CredentialLease).where(
            CredentialLease.run_id == run_id,
            CredentialLease.credential_id == credential.id,
            CredentialLease.credential_version == credential.version,
        )
    )
    if lease is not None:
        if lease.revoked_at is not None or lease.expires_at <= now():
            raise CredentialRevoked()
        return lease  # Never extend a grant by re-resolving a run.
    lease = CredentialLease(
        id=new_id(),
        org_id=credential.org_id,
        run_id=run_id,
        credential_id=credential.id,
        credential_version=credential.version,
        expires_at=now() + timedelta(seconds=LEASE_SECONDS),
    )
    session.add(lease)
    await session.flush()
    return lease


async def check(run_id: str) -> None:
    async with SessionFactory() as session:
        await bind_run_organization(session, run_id)
        run = await session.get(Run, run_id)
        slot = await session.get(CallAdmission, 1)
        if (
            slot is None
            or slot.run_id != run_id
            or slot.expires_at is None
            or slot.expires_at <= now()
        ):
            raise CredentialRevoked()
        rows = (
            await session.execute(
                select(CredentialLease, ProviderCredential)
                .join(ProviderCredential, ProviderCredential.id == CredentialLease.credential_id)
                .where(CredentialLease.run_id == run_id)
            )
        ).all()
        expected = {
            ref["credential_id"]
            for ref in run.resolved_config.get("_resolved", {}).get("credentials", {}).values()
        }
        if expected - {credential.id for _, credential in rows}:
            raise CredentialRevoked()
        for lease, credential in rows:
            if (
                lease.revoked_at is not None
                or lease.expires_at <= now()
                or credential.status != "stored"
            ):
                raise CredentialRevoked()


async def guard(run_id: str, operation, *, timeout_secs: float):
    """Cancel provider work on revocation; existing owners perform normal cleanup."""

    async def execute():
        await check(run_id)
        async with asyncio.timeout(timeout_secs):
            return await operation()

    async def watch():
        while True:
            await asyncio.sleep(1)
            await check(run_id)

    work, watcher = asyncio.create_task(execute()), asyncio.create_task(watch())
    try:
        done, _ = await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if watcher in done:
            await watcher
        return await work
    finally:
        work.cancel()
        watcher.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


async def release(run_id: str) -> None:
    from fastapi import HTTPException
    from sqlalchemy import update

    async with SessionFactory() as session:
        try:
            await bind_run_organization(session, run_id)
        except HTTPException as error:
            if error.status_code == 404:
                return  # Run deletion cascades its grants and clears admission FK.
            raise
        slot = await session.get(CallAdmission, 1, with_for_update=True)
        if slot is not None and slot.run_id == run_id:
            slot.run_id, slot.expires_at = None, None
        await session.execute(
            update(CredentialLease)
            .where(CredentialLease.run_id == run_id, CredentialLease.revoked_at.is_(None))
            .values(revoked_at=now())
        )
        await session.commit()
