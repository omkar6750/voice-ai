from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import Contact, ContactFact, Run
from voice_api.schemas.contact import ContactBody, ContactPatchBody

router = APIRouter(tags=["contacts"])
Session = Depends(get_session)
Operator = Depends(require_operator)


def contact_summary(contact: Contact) -> dict:
    return {
        "id": contact.id,
        "name": contact.name,
        "phone_number": contact.phone_number,
        "timezone": contact.timezone,
        "business": contact.business,
        "source": contact.source,
        "language": contact.language,
        "metadata": contact.metadata_json,
        "created_at": contact.created_at.isoformat() if contact.created_at else None,
    }


@router.get("/contacts")
async def contacts(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Contact).order_by(Contact.created_at.desc()))).all()
    return {"contacts": [contact_summary(x) for x in rows]}


@router.post("/contacts", status_code=201)
async def create_contact(
    body: ContactBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = Contact(**body.model_dump())
    session.add(row)
    await session.commit()
    return {"id": row.id}


@router.get("/contacts/{contact_id}")
async def get_contact(contact_id: str, session: AsyncSession = Session, _: None = Operator) -> dict:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Contact not found")

    facts = (
        await session.scalars(
            select(ContactFact)
            .where(ContactFact.contact_id == contact_id)
            .order_by(ContactFact.occurred_at.desc(), ContactFact.created_at.desc())
        )
    ).all()

    runs = (
        await session.scalars(
            select(Run)
            .where(Run.contact_id == contact_id)
            .order_by(Run.created_at.desc())
            .limit(50)
        )
    ).all()

    summary = contact_summary(contact)
    summary["facts"] = [
        {
            "id": f.id,
            "name": f.name,
            "value": f.value,
            "run_id": f.run_id,
            "supersedes_id": f.supersedes_id,
            "occurred_at": f.occurred_at.isoformat() if f.occurred_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
        for f in facts
    ]
    summary["runs"] = [
        {
            "id": r.id,
            "status": r.status,
            "channel": r.channel,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "error": r.error,
        }
        for r in runs
    ]
    return summary


@router.patch("/contacts/{contact_id}")
async def update_contact(
    contact_id: str,
    body: ContactPatchBody,
    session: AsyncSession = Session,
    _: None = Operator,
) -> dict:
    contact = await session.get(Contact, contact_id, with_for_update=True)
    if contact is None:
        raise HTTPException(404, "Contact not found")

    if body.phone_number is not None and body.phone_number != contact.phone_number:
        existing = await session.scalar(
            select(Contact).where(
                Contact.phone_number == body.phone_number, Contact.id != contact_id
            )
        )
        if existing:
            raise HTTPException(409, "Phone number already registered to another contact")
        contact.phone_number = body.phone_number

    if body.name is not None:
        contact.name = body.name.strip()
    if body.timezone is not None:
        contact.timezone = body.timezone
    if body.business is not None:
        contact.business = body.business.strip() or None
    if body.source is not None:
        contact.source = body.source.strip() or None
    if body.language is not None:
        contact.language = body.language.strip() or None
    if body.metadata_json is not None:
        contact.metadata_json = body.metadata_json

    await session.commit()
    return contact_summary(contact)
