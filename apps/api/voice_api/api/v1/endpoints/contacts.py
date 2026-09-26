from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import Call, Callback, Contact, ContactFact, Run
from voice_api.schemas.contact import (
    ContactBody,
    ContactPatchBody,
    ContactVariablesResponse,
    VariableDescriptor,
)

router = APIRouter(tags=["contacts"])
Session = Depends(get_session)
Operator = Depends(require_operator)

BLOCKED_CONTACT_FIELDS = {"id", "phone_number", "metadata_json", "created_at"}

TEMPORAL_VARIABLE_DESCRIPTORS = [
    VariableDescriptor(
        key="greeting_phrase",
        label="Greeting phrase",
        source="temporal",
        description="Good morning / afternoon / evening based on contact timezone",
    ),
    VariableDescriptor(
        key="signoff_phrase",
        label="Signoff phrase",
        source="temporal",
        description="Parting phrase matching contact local time",
    ),
    VariableDescriptor(
        key="local_time_12h",
        label="Local time (12h)",
        source="temporal",
        description="e.g. 2:30 PM in contact timezone",
    ),
    VariableDescriptor(
        key="local_time_24h",
        label="Local time (24h)",
        source="temporal",
        description="e.g. 14:30 in contact timezone",
    ),
    VariableDescriptor(
        key="daypart",
        label="Daypart",
        source="temporal",
        description="morning, afternoon, evening, or night",
    ),
    VariableDescriptor(
        key="day_of_week",
        label="Day of week",
        source="temporal",
        description="e.g. Monday in contact timezone",
    ),
    VariableDescriptor(
        key="country",
        label="Country name",
        source="temporal",
        description="e.g. India, United States, United Kingdom (derived from contact timezone)",
    ),
    VariableDescriptor(
        key="country_code",
        label="Country code (ISO)",
        source="temporal",
        description="e.g. IN, US, GB (derived from contact timezone)",
    ),
]


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


@router.get("/contacts/variables", response_model=ContactVariablesResponse)
async def get_contact_variables(
    session: AsyncSession = Session, _: None = Operator
) -> ContactVariablesResponse:
    # 1. Introspect columns on Contact table
    columns: list[VariableDescriptor] = []
    for col in Contact.__table__.columns:
        if col.name not in BLOCKED_CONTACT_FIELDS:
            columns.append(
                VariableDescriptor(
                    key=col.name,
                    label=col.name.replace("_", " ").title(),
                    source="column",
                    description=f"Contact {col.name.replace('_', ' ')} from database",
                )
            )

    # 2. Distinct keys stored in JSONB metadata
    metadata_keys: list[VariableDescriptor] = []
    try:
        result = await session.execute(
            text(
                "SELECT DISTINCT jsonb_object_keys(metadata_json) AS key "
                "FROM contacts "
                "WHERE metadata_json IS NOT NULL AND metadata_json != '{}'::jsonb "
                "ORDER BY key"
            )
        )
        for row in result.fetchall():
            key = str(row[0])
            metadata_keys.append(
                VariableDescriptor(
                    key=key,
                    label=key.replace("_", " ").title(),
                    source="metadata",
                    description=f"Ad / lead metadata field '{key}'",
                )
            )
    except Exception:
        # Fallback if DB table is empty or non-postgres dialect in tests
        pass

    return ContactVariablesResponse(
        columns=columns,
        metadata_keys=metadata_keys,
        temporal=TEMPORAL_VARIABLE_DESCRIPTORS,
    )


@router.post("/contacts", status_code=201)
async def create_contact(
    body: ContactBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    data = body.model_dump()
    if data.get("metadata_json") is None:
        data["metadata_json"] = {}
    row = Contact(**data)
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


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: str, session: AsyncSession = Session, _: None = Operator
) -> None:
    row = await session.get(Contact, contact_id)
    if row is None:
        raise HTTPException(404, "Contact not found")
    await session.execute(delete(Callback).where(Callback.contact_id == contact_id))
    calls = (await session.scalars(select(Call).where(Call.contact_id == contact_id))).all()
    run_ids = [call.run_id for call in calls if call.run_id]
    for call in calls:
        await session.delete(call)
    await session.flush()
    for run_id in run_ids:
        await session.execute(delete(Run).where(Run.id == run_id))
    await session.execute(delete(Run).where(Run.contact_id == contact_id))
    await session.delete(row)
    await session.commit()
