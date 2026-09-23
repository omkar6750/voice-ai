from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_operator
from voice_api.models import Contact
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
