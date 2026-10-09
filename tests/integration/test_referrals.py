"""Referral writes stay separate from dialable contacts and preserve their provenance."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import Agent, AgentVersion, Contact, Organization, Referral, Run, User
from voice_api.schemas.referrals import ReferralReview
from voice_api.services.referral_service import (
    install_referral_tool,
    promote_referral,
    review_referral,
    save_referral,
)
from voice_api.services.runtime_tools import BackendToolDispatch
from voice_runtime.contracts.referrals import SaveReferralArguments


async def make_run(database):
    contact = Contact(
        name="Original Caller",
        first_name="Original",
        last_name="Caller",
        phone_number="+919876543210",
    )
    agent = Agent(name=f"referral-test-{uuid4()}")
    database.add_all([contact, agent])
    await database.flush()
    version = AgentVersion(agent_id=agent.id, version=1, config={})
    database.add(version)
    await database.flush()
    run = Run(agent_version_id=version.id, contact_id=contact.id, resolved_config={})
    database.add(run)
    await database.flush()
    return run, contact


@pytest.mark.parametrize(
    "details",
    [
        {},
        {"email": "sales@example.com"},
        {"phone_number": "9876543210"},
        {"phone_number": "+919876543211", "email": "sales@example.com"},
    ],
)
async def test_capture_optional_details_idempotency_and_no_contact_creation(database, details):
    run, caller = await make_run(database)
    args = SaveReferralArguments(
        first_name="  Asha  ", contact_details_confirmed=bool(details), **details
    )
    row = await save_referral(database, run_id=run.id, invocation_id="call-1", arguments=args)
    again = await save_referral(database, run_id=run.id, invocation_id="call-1", arguments=args)
    assert row.id == again.id and row.first_name == "Asha"
    assert row.referrer_contact_id == caller.id and row.source_run_id == run.id
    assert row.phone_verification_status == row.email_verification_status == "unverified"
    assert len((await database.scalars(select(Contact))).all()) == 1
    with pytest.raises(HTTPException, match="different referral"):
        await save_referral(
            database,
            run_id=run.id,
            invocation_id="call-1",
            arguments=SaveReferralArguments(first_name="Other"),
        )


async def test_readback_guard_review_conflict_and_promotion(database):
    run, _ = await make_run(database)
    with pytest.raises(HTTPException, match="Read back"):
        await save_referral(
            database,
            run_id=run.id,
            invocation_id="call-1",
            arguments=SaveReferralArguments(first_name="Asha", phone_number="+919876543211"),
        )
    row = await save_referral(
        database,
        run_id=run.id,
        invocation_id="call-1",
        arguments=SaveReferralArguments(
            first_name="Asha", phone_number="+919876543211", contact_details_confirmed=True
        ),
    )
    with pytest.raises(HTTPException, match="verify"):
        await promote_referral(database, row.id)
    body = ReferralReview(
        first_name="Asha",
        phone_number="+919876543211",
        contact_details_confirmed=True,
        phone_verification_status="verified",
        expected_updated_at=row.updated_at,
        status="reviewed",
    )
    await review_referral(database, row.id, body)
    with pytest.raises(HTTPException, match="changed"):
        await review_referral(database, row.id, body)
    contact, existing = await promote_referral(database, row.id)
    assert not existing and contact.first_name == "Asha" and row.status == "converted"
    again, existing = await promote_referral(database, row.id)
    assert existing and again.id == contact.id


async def test_referral_survives_cleanup_and_other_scope_cannot_read(database):
    run, caller = await make_run(database)
    row = await save_referral(
        database,
        run_id=run.id,
        invocation_id="call-1",
        arguments=SaveReferralArguments(first_name="Asha"),
    )
    await database.execute(delete(Run).where(Run.id == run.id))
    await database.execute(delete(Contact).where(Contact.id == caller.id))
    await database.refresh(row)
    assert row.source_run_id is None and row.referrer_contact_id is None
    async with AsyncSession(
        bind=await database.connection(), join_transaction_mode="create_savepoint"
    ) as other:
        bind_organization(other.sync_session, "other-organization")
        assert (await other.scalars(select(Referral))).all() == []


async def test_install_and_api_review(database, client):
    first = await install_referral_tool(database)
    second = await install_referral_tool(database)
    assert first == second
    run, _ = await make_run(database)
    row = await save_referral(
        database,
        run_id=run.id,
        invocation_id="call-1",
        arguments=SaveReferralArguments(
            first_name="Asha", email="asha@example.com", contact_details_confirmed=True
        ),
    )
    response = await client.get("/api/v1/referrals")
    assert response.status_code == 200 and response.json()["referrals"][0]["id"] == row.id
    response = await client.post(f"/api/v1/referrals/{row.id}/promote")
    assert response.status_code == 422


async def test_backend_tool_alias_uses_run_scope_and_returns_saved_result(database, monkeypatch):
    run, _ = await make_run(database)

    @asynccontextmanager
    async def factory():
        yield database

    monkeypatch.setattr("voice_api.db.session.SessionFactory", factory)
    dispatch = BackendToolDispatch()
    dispatch.run_id = run.id
    dispatch._snapshot = {
        "_resolved": {"tools": {"capture_person": {"definition": {"handler": "save_referral"}}}}
    }
    manager = SimpleNamespace(active_tool_invocation_id="referral-invocation")
    result = await dispatch._handler("capture_person")({"first_name": "Asha"}, manager)
    assert result["status"] == "saved"
    assert result["referral"]["source_run_id"] == run.id
    retry = await dispatch._handler("capture_person")({"first_name": "Asha"}, manager)
    assert retry["referral_id"] == result["referral_id"]
    error = await dispatch._handler("capture_person")(
        {"first_name": "Asha", "email": "asha@example.com"}, manager
    )
    assert error["status"] == "error" and "Read back" in error["error"]


async def test_cross_org_reference_is_rejected_by_database(database):
    user = User(clerk_user_id=f"referral-user-{uuid4()}")
    database.add(user)
    await database.flush()
    org = Organization(
        clerk_org_id=f"referral-org-{uuid4()}", name="Other tenant", owner_user_id=user.id
    )
    database.add(org)
    await database.flush()
    async with AsyncSession(
        bind=await database.connection(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as other:
        bind_organization(other.sync_session, org.id)
        contact = Contact(name="Other", phone_number="+919876543222")
        other.add(contact)
        await other.commit()
        other_id = contact.id
    with pytest.raises(IntegrityError):
        async with database.begin_nested():
            database.add(
                Referral(
                    first_name="Asha",
                    source_invocation_id="bad-ref",
                    request_hash="x" * 64,
                    referrer_contact_id=other_id,
                )
            )
            await database.flush()


async def test_api_review_verification_and_existing_contact_link(database, client):
    run, caller = await make_run(database)
    row = await save_referral(
        database,
        run_id=run.id,
        invocation_id="call-api",
        arguments=SaveReferralArguments(
            first_name="Asha", phone_number=caller.phone_number, contact_details_confirmed=True
        ),
    )
    response = await client.patch(
        f"/api/v1/referrals/{row.id}",
        json={
            "first_name": "Asha",
            "phone_number": caller.phone_number,
            "phone_verification_status": "verified",
            "status": "reviewed",
            "expected_updated_at": row.updated_at.isoformat(),
        },
    )
    assert response.status_code == 200
    response = await client.post(f"/api/v1/referrals/{row.id}/promote")
    assert response.status_code == 200 and response.json()["existing_contact"]
    assert response.json()["contact_id"] == caller.id
    await database.refresh(caller)
    assert caller.name == "Original Caller"
