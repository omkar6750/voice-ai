"""Capture unverified referrals and explicitly review them before promotion."""

import hashlib
import json
import re
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts.referrals import SaveReferralArguments
from voice_runtime.contracts.tools import ToolConfig

from voice_api.db.tenant_scope import required_organization
from voice_api.models import Contact, Organization, Referral, Run, Tool, ToolVersion
from voice_api.schemas.contact import ContactBody
from voice_api.schemas.referrals import ReferralReview, ReferralToolResponse


async def get_referral(session: AsyncSession, referral_id: str) -> Referral:
    row = await session.scalar(select(Referral).where(Referral.id == referral_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Referral not found")
    return row


async def save_referral(
    session: AsyncSession, *, run_id: str, invocation_id: str, arguments: SaveReferralArguments
) -> Referral:
    if (arguments.phone_number or arguments.email) and not arguments.contact_details_confirmed:
        raise HTTPException(
            422, "Read back the supplied phone/email and wait for confirmation before saving"
        )
    if not invocation_id or len(invocation_id) > 120:
        raise HTTPException(422, "A valid tool invocation ID is required")
    # Serialize writes for this run; a retry must return the original record.
    run = await session.scalar(select(Run).where(Run.id == run_id).with_for_update())
    if run is None:
        raise HTTPException(404, "Source run not found")
    digest = hashlib.sha256(json.dumps(arguments.model_dump(), sort_keys=True).encode()).hexdigest()
    existing = await session.scalar(
        select(Referral).where(Referral.source_invocation_id == invocation_id)
    )
    if existing:
        if existing.request_hash != digest or existing.source_run_id != run_id:
            raise HTTPException(409, "This invocation already saved different referral details")
        return existing
    row = Referral(
        source_run_id=run.id,
        referrer_contact_id=run.contact_id,
        source_invocation_id=invocation_id,
        request_hash=digest,
        **arguments.model_dump(),
    )
    session.add(row)
    await session.flush()
    return row


async def review_referral(
    session: AsyncSession, referral_id: str, body: ReferralReview
) -> Referral:
    row = await get_referral(session, referral_id)
    if row.status == "converted":
        raise HTTPException(409, "Converted referrals cannot be edited")
    if row.updated_at != body.expected_updated_at:
        raise HTTPException(409, "Referral changed; reload before saving")
    if body.phone_verification_status == "verified":
        if not body.phone_number:
            raise HTTPException(422, "A phone number is required to mark it verified")
        try:
            body.phone_number = ContactBody.normalize_phone(body.phone_number)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
    if body.email_verification_status == "verified" and (
        not body.email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", body.email)
    ):
        raise HTTPException(422, "A valid email address is required to mark it verified")
    # Operators cannot create caller confirmation, and edited details were not
    # the ones the caller read back. The original tool evidence is preserved.
    body.contact_details_confirmed = bool(
        row.contact_details_confirmed
        and row.phone_number == body.phone_number
        and row.email == body.email
    )
    for key, value in body.model_dump(exclude={"expected_updated_at"}).items():
        setattr(row, key, value)
    await session.flush()
    return row


async def promote_referral(session: AsyncSession, referral_id: str) -> tuple[Contact, bool]:
    # Organization lock prevents concurrent promotions from racing on the contact phone unique key.
    await session.scalar(
        select(Organization)
        .where(Organization.id == required_organization(session))
        .with_for_update()
    )
    row = await get_referral(session, referral_id)
    if row.status == "converted":
        contact = (
            await session.get(Contact, row.promoted_contact_id) if row.promoted_contact_id else None
        )
        if contact is None:
            raise HTTPException(409, "Previously created contact has been removed")
        return contact, True
    if (
        row.status == "dismissed"
        or row.phone_verification_status != "verified"
        or not row.phone_number
    ):
        raise HTTPException(
            422, "Review and verify an international phone number before creating a contact"
        )
    try:
        phone = ContactBody.normalize_phone(row.phone_number)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    contact = await session.scalar(select(Contact).where(Contact.phone_number == phone))
    existing = contact is not None
    if contact is None:
        full_name = " ".join(part for part in (row.first_name, row.last_name) if part)
        if len(full_name) > 120:
            raise HTTPException(422, "Contact display name must be at most 120 characters")
        contact = Contact(
            first_name=row.first_name,
            last_name=row.last_name,
            name=full_name,
            phone_number=phone,
            business=row.organization,
            source="referral",
            metadata_json={
                "referral_id": row.id,
                "email": row.email,
                "email_verification_status": row.email_verification_status,
                "role": row.role,
            },
        )
        try:
            async with session.begin_nested():
                session.add(contact)
                await session.flush()
        except IntegrityError:
            contact = await session.scalar(select(Contact).where(Contact.phone_number == phone))
            if contact is None:
                raise
            existing = True
    row.status = "converted"
    row.promoted_contact_id = contact.id
    await session.flush()
    return contact, existing


async def install_referral_tool(session: AsyncSession) -> ReferralToolResponse:
    await session.scalar(
        select(Organization)
        .where(Organization.id == required_organization(session))
        .with_for_update()
    )
    tool = await session.scalar(select(Tool).where(Tool.name == "save_referral"))
    if tool is None:
        tool = Tool(name="save_referral")
        session.add(tool)
        await session.flush()
    elif tool.archived_at is not None:
        raise HTTPException(409, "Restore the archived save_referral tool first")
    version = await session.scalar(
        select(ToolVersion)
        .where(ToolVersion.tool_id == tool.id)
        .order_by(ToolVersion.version.desc())
        .limit(1)
    )
    config = ToolConfig(name="save_referral", handler="save_referral").model_dump(mode="json")
    if version is None or version.status != "published" or version.config != config:
        version = ToolVersion(
            tool_id=tool.id,
            version=(version.version + 1 if version else 1),
            status="published",
            published_at=datetime.now(UTC),
            config=config,
        )
        session.add(version)
        await session.flush()
    return ReferralToolResponse(tool_id=tool.id, tool_version_id=version.id)
