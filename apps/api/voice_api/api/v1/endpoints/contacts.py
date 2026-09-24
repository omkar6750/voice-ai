from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import Call, Callback, Contact, Run
from voice_api.schemas.contact import ContactBody

router = APIRouter(tags=["contacts"])
Session = Depends(get_session)
Operator = Depends(require_operator)


@router.get("/contacts")
async def contacts(session: AsyncSession = Session, _: None = Operator) -> dict:
    rows = (await session.scalars(select(Contact).order_by(Contact.created_at.desc()))).all()
    return {
        "contacts": [
            {
                "id": x.id,
                "name": x.name,
                "phone_number": x.phone_number,
                "timezone": x.timezone,
                "business": x.business,
                "source": x.source,
                "language": x.language,
            }
            for x in rows
        ]
    }


@router.post("/contacts", status_code=201)
async def create_contact(
    body: ContactBody, session: AsyncSession = Session, _: None = Operator
) -> dict:
    row = Contact(**body.model_dump())
    session.add(row)
    await session.commit()
    return {"id": row.id}


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(
    contact_id: str, session: AsyncSession = Session, _: None = Operator
) -> None:
    row = await session.get(Contact, contact_id)
    if row is None:
        raise HTTPException(404, "Contact not found")
    await session.execute(delete(Callback).where(Callback.contact_id == contact_id))
    calls = (await session.scalars(select(Call).where(Call.contact_id == contact_id))).all()
    run_ids = [c.run_id for c in calls if c.run_id]
    for c in calls:
        await session.delete(c)
    await session.flush()
    for r_id in run_ids:
        await session.execute(delete(Run).where(Run.id == r_id))
    await session.execute(delete(Run).where(Run.contact_id == contact_id))
    await session.delete(row)
    await session.commit()

