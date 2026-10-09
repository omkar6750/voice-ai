from fastapi import APIRouter
from voice_api.api.v1.endpoints import (
    agents_router,
    analysis_router,
    artifacts_router,
    browser_sessions_router,
    callbacks_router,
    calls_router,
    contacts_router,
    evidence_router,
    execution_router,
    integrations_router,
    knowledge_router,
    providers_router,
    reconciliation_router,
    runs_router,
    telephony_router,
    tools_router,
    workspace_router,
)
from voice_api.api.v1.endpoints.auth import router as auth_router
from voice_api.api.v1.endpoints.calendar import router as calendar_router
from voice_api.api.v1.endpoints.dial_catalog import router as dial_catalog_router
from voice_api.api.v1.endpoints.mcp_tokens import router as mcp_tokens_router
from voice_api.api.v1.endpoints.openrouter import router as openrouter_router
from voice_api.api.v1.endpoints.organizations import router as organizations_router
from voice_api.api.v1.endpoints.platform import router as platform_router
from voice_api.api.v1.endpoints.recordings import router as recordings_router
from voice_api.api.v1.endpoints.referrals import router as referrals_router
from voice_api.api.v1.endpoints.run_debug import router as run_debug_router
from voice_api.core.runtime_config import use_separate_runtime

api_router = APIRouter()
api_router.include_router(mcp_tokens_router)
api_router.include_router(run_debug_router)

api_router.include_router(auth_router)
api_router.include_router(organizations_router)
api_router.include_router(openrouter_router)
api_router.include_router(platform_router)
api_router.include_router(providers_router)
api_router.include_router(workspace_router)
api_router.include_router(agents_router)
api_router.include_router(tools_router)
api_router.include_router(contacts_router)
api_router.include_router(referrals_router)
api_router.include_router(calls_router)
api_router.include_router(dial_catalog_router)
api_router.include_router(runs_router)
api_router.include_router(execution_router)
api_router.include_router(evidence_router)
api_router.include_router(analysis_router)
api_router.include_router(artifacts_router)
api_router.include_router(recordings_router)
api_router.include_router(callbacks_router)
api_router.include_router(reconciliation_router)
api_router.include_router(knowledge_router)
api_router.include_router(integrations_router)
api_router.include_router(calendar_router)
api_router.include_router(telephony_router)
api_router.include_router(browser_sessions_router)


if use_separate_runtime():
    from voice_api.api.v1.endpoints.chat import router as chat_router
    from voice_api.api.v1.endpoints.runtime import router as runtime_router
    from voice_api.api.v1.endpoints.runtime_artifacts import router as runtime_artifacts_router

    api_router.include_router(chat_router)
    api_router.include_router(runtime_router)
    api_router.include_router(runtime_artifacts_router)
