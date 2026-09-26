from fastapi import APIRouter
from voice_api.api.v1.endpoints import (
    agents_router,
    analysis_router,
    artifacts_router,
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
from voice_api.api.v1.endpoints.calendar import router as calendar_router
from voice_api.api.v1.endpoints.dial_catalog import router as dial_catalog_router

api_router = APIRouter()

api_router.include_router(providers_router)
api_router.include_router(workspace_router)
api_router.include_router(agents_router)
api_router.include_router(tools_router)
api_router.include_router(contacts_router)
api_router.include_router(calls_router)
api_router.include_router(dial_catalog_router)
api_router.include_router(runs_router)
api_router.include_router(execution_router)
api_router.include_router(evidence_router)
api_router.include_router(analysis_router)
api_router.include_router(artifacts_router)
api_router.include_router(callbacks_router)
api_router.include_router(reconciliation_router)
api_router.include_router(knowledge_router)
api_router.include_router(integrations_router)
api_router.include_router(calendar_router)
api_router.include_router(telephony_router)
