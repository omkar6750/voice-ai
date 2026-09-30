"""Organization-scoped OpenRouter catalog and account endpoints."""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.v1.endpoints.organizations import _registered_org
from voice_api.core.clerk_auth import ClerkPrincipal, require_clerk_user
from voice_api.core.clerk_organizations import (
    ClerkOrganizationDirectory,
    get_clerk_organization_directory,
)
from voice_api.db.session import get_session
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import User
from voice_api.schemas.providers import (
    ModelCatalogResponse,
    OpenRouterAccountResponse,
    OpenRouterEndpointCatalogResponse,
    OpenRouterEndpointResponse,
    OpenRouterModelQuery,
)
from voice_api.services import credential_service
from voice_api.services.credential_service import credential_scope
from voice_api.services.openrouter_catalog import account_status, model_catalog
from voice_api.services.openrouter_client import OpenRouterClient, OpenRouterError
from voice_api.services.provider_credentials import decrypt_provider_key
from voice_api.services.vault_service import VaultError

router = APIRouter(prefix="/orgs", tags=["openrouter"])
Principal = Depends(require_clerk_user)
Session = Depends(get_session)
Directory = Depends(get_clerk_organization_directory)


async def _openrouter_client(
    org_id: str,
    credential_id: str,
    principal: ClerkPrincipal,
    session: AsyncSession,
    directory: ClerkOrganizationDirectory,
    *,
    admin_required: bool = False,
) -> OpenRouterClient:
    organization, membership = await _registered_org(org_id, session, directory, principal)
    if admin_required:
        if membership.role not in {"org:owner", "org:admin"}:
            raise HTTPException(403, "Organization admin required")
        actor_exists = await session.scalar(
            select(User.id).where(User.clerk_user_id == principal.user_id)
        )
        if actor_exists is None:
            raise HTTPException(409, "Refresh your account profile before viewing account usage")
    bind_organization(session.sync_session, organization.id)
    row = await credential_service.lookup(session, credential_id)
    if row.provider != "openrouter" or row.status != "stored":
        raise HTTPException(422, "Credential is not an active OpenRouter credential")
    try:
        key = decrypt_provider_key(
            row.provider, row.ciphertext, row.key_id, scope=credential_scope(row)
        )
    except VaultError as error:
        raise HTTPException(503, "OpenRouter credential is unavailable") from error
    return OpenRouterClient(key)


def _http_error(error: OpenRouterError) -> HTTPException:
    status = error.status_code if 400 <= error.status_code < 500 else 502
    return HTTPException(
        status,
        detail={"category": error.category, "metadata_keys": list(error.metadata_keys)},
    )


@router.get(
    "/{org_id}/openrouter/{credential_id}/account",
    response_model=OpenRouterAccountResponse,
)
async def openrouter_account(
    org_id: str,
    credential_id: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OpenRouterAccountResponse:
    client = await _openrouter_client(
        org_id, credential_id, principal, session, directory, admin_required=True
    )
    return await account_status(client, credential_id)


@router.get(
    "/{org_id}/openrouter/{credential_id}/models",
    response_model=ModelCatalogResponse,
)
async def openrouter_models(
    org_id: str,
    credential_id: str,
    q: str | None = Query(default=None, max_length=120),
    free_only: bool | None = None,
    author: str | None = Query(default=None, max_length=120),
    tool_calling: bool | None = None,
    structured_output: bool | None = None,
    reasoning: bool | None = None,
    min_context: int | None = Query(default=None, ge=1),
    max_prompt_price: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=1000),
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> ModelCatalogResponse:
    try:
        price = Decimal(max_prompt_price) if max_prompt_price is not None else None
    except InvalidOperation as error:
        raise HTTPException(422, "max_prompt_price must be a decimal") from error
    client = await _openrouter_client(org_id, credential_id, principal, session, directory)
    try:
        return await model_catalog(
            client,
            OpenRouterModelQuery(
                q=q,
                free_only=free_only,
                author=author,
                tool_calling=tool_calling,
                structured_output=structured_output,
                reasoning=reasoning,
                min_context=min_context,
                max_prompt_price=price,
                offset=offset,
                limit=limit,
            ),
        )
    except OpenRouterError as error:
        raise _http_error(error) from error


@router.get(
    "/{org_id}/openrouter/{credential_id}/models/{author}/{slug}/endpoints",
    response_model=OpenRouterEndpointCatalogResponse,
)
async def openrouter_model_endpoints(
    org_id: str,
    credential_id: str,
    author: str,
    slug: str,
    principal: ClerkPrincipal = Principal,
    session: AsyncSession = Session,
    directory: ClerkOrganizationDirectory = Directory,
) -> OpenRouterEndpointCatalogResponse:
    client = await _openrouter_client(org_id, credential_id, principal, session, directory)
    try:
        page = await client.endpoints(author, slug)
    except OpenRouterError as error:
        raise _http_error(error) from error
    return OpenRouterEndpointCatalogResponse(
        model_id=page.data.get("id", f"{author}/{slug}"),
        endpoints=[
            OpenRouterEndpointResponse.model_validate(endpoint.model_dump())
            for endpoint in page.endpoints
        ],
        checked_at=datetime.now(UTC),
    )
