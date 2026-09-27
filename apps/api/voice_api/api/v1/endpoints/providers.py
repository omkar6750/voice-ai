from fastapi import APIRouter, Depends
from voice_api.api.deps import Settings, SettingsDep, require_operator
from voice_api.schemas.providers import ProviderCatalogResponse
from voice_api.services.provider_registry import get_provider_registry
from voice_runtime.contracts import AgentConfig, ToolConfig, WorkspaceConfig

router = APIRouter(tags=["providers"])
Operator = Depends(require_operator)


@router.get("/providers", response_model=ProviderCatalogResponse)
async def providers(
    settings: Settings = SettingsDep, _: None = Operator
) -> ProviderCatalogResponse:
    return await get_provider_registry(settings)


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
