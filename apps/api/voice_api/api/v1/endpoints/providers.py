from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.api.deps import Settings, SettingsDep, require_legacy_owner
from voice_api.db.session import get_session
from voice_api.db.tenant_scope import required_organization
from voice_api.schemas.providers import ProviderCatalogResponse
from voice_api.services.provider_credentials import settings_for_organization
from voice_api.services.provider_registry import get_provider_registry
from voice_runtime.contracts import AgentConfig, ToolConfig, WorkspaceConfig

router = APIRouter(tags=["providers"])
Operator = Depends(require_legacy_owner)
Session = Depends(get_session)


@router.get("/providers", response_model=ProviderCatalogResponse)
async def providers(
    settings: Settings = SettingsDep,
    session: AsyncSession = Session,
    _: None = Operator,
) -> ProviderCatalogResponse:
    organization_id = required_organization(session.sync_session)
    scoped_settings = await settings_for_organization(session, organization_id, settings)
    return await get_provider_registry(scoped_settings)


@router.get("/config-schema")
async def config_schema(_: None = Operator) -> dict:
    return {
        "agent": AgentConfig.model_json_schema(),
        "tool": ToolConfig.model_json_schema(),
        "workspace": WorkspaceConfig.model_json_schema(),
        "runtime_application": {
            "prompt": "applied",
            "flow": "applied",
            "model": "applied",
            "tools": "applied",
            "classifier": "pending_runner",
            "summarizer": "pending_runner",
            "audio": "pending_runner",
        },
    }
