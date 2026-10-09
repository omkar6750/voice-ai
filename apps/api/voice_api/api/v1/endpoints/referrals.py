from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import get_session, require_legacy_owner
from voice_api.core.security import allow_organization_member
from voice_api.models import Referral
from voice_api.schemas.referrals import (
    ReferralPage,
    ReferralPromotionResponse,
    ReferralResponse,
    ReferralReview,
    ReferralToolResponse,
)
from voice_api.services.referral_service import (
    get_referral,
    install_referral_tool,
    promote_referral,
    review_referral,
)

router = APIRouter(tags=["referrals"])
Session = Depends(get_session)
Operator = Depends(require_legacy_owner)


@router.get("/referrals", response_model=ReferralPage)
@allow_organization_member
async def list_referrals(
    status: Literal["pending_review", "reviewed", "dismissed", "converted"] | None = None,
    referrer_contact_id: str | None = None,
    source_run_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Session,
    _: None = Operator,
) -> ReferralPage:
    query = select(Referral)
    if status:
        query = query.where(Referral.status == status)
    if referrer_contact_id:
        query = query.where(Referral.referrer_contact_id == referrer_contact_id)
    if source_run_id:
        query = query.where(Referral.source_run_id == source_run_id)
    if cursor:
        query = query.where(Referral.id > cursor)
    rows = (await session.scalars(query.order_by(Referral.id).limit(limit + 1))).all()
    return ReferralPage(
        referrals=[ReferralResponse.model_validate(row) for row in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.post("/referrals/tool", response_model=ReferralToolResponse)
async def install_tool(session: AsyncSession = Session, _: None = Operator) -> ReferralToolResponse:
    result = await install_referral_tool(session)
    await session.commit()
    return result


@router.get("/referrals/{referral_id}", response_model=ReferralResponse)
@allow_organization_member
async def referral(
    referral_id: str, session: AsyncSession = Session, _: None = Operator
) -> ReferralResponse:
    return ReferralResponse.model_validate(await get_referral(session, referral_id))


@router.patch("/referrals/{referral_id}", response_model=ReferralResponse)
async def review(
    referral_id: str, body: ReferralReview, session: AsyncSession = Session, _: None = Operator
) -> ReferralResponse:
    row = await review_referral(session, referral_id, body)
    result = ReferralResponse.model_validate(row)
    await session.commit()
    return result


@router.post("/referrals/{referral_id}/promote", response_model=ReferralPromotionResponse)
async def promote(
    referral_id: str, session: AsyncSession = Session, _: None = Operator
) -> ReferralPromotionResponse:
    contact, existing = await promote_referral(session, referral_id)
    result = ReferralPromotionResponse(contact_id=contact.id, existing_contact=existing)
    await session.commit()
    return result
