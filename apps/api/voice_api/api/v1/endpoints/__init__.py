from voice_api.core.runtime_config import use_separate_runtime

if use_separate_runtime():
    from voice_api.api.v1.endpoints.remote_browser_sessions import router as browser_sessions_router
    from voice_api.api.v1.endpoints.remote_calls import router as calls_router
    from voice_api.api.v1.endpoints.remote_execution import router as execution_router
    from voice_api.api.v1.endpoints.remote_telephony import router as telephony_router
else:
    from voice_api.api.v1.endpoints.browser_sessions import router as browser_sessions_router
    from voice_api.api.v1.endpoints.calls import router as calls_router
    from voice_api.api.v1.endpoints.execution import router as execution_router
    from voice_api.api.v1.endpoints.telephony import router as telephony_router

from voice_api.api.v1.endpoints.agents import router as agents_router
from voice_api.api.v1.endpoints.analysis import router as analysis_router
from voice_api.api.v1.endpoints.artifacts import router as artifacts_router
from voice_api.api.v1.endpoints.callbacks import router as callbacks_router
from voice_api.api.v1.endpoints.contacts import router as contacts_router
from voice_api.api.v1.endpoints.evidence import router as evidence_router
from voice_api.api.v1.endpoints.integrations import router as integrations_router
from voice_api.api.v1.endpoints.knowledge import router as knowledge_router
from voice_api.api.v1.endpoints.providers import router as providers_router
from voice_api.api.v1.endpoints.reconciliation import router as reconciliation_router
from voice_api.api.v1.endpoints.runs import router as runs_router
from voice_api.api.v1.endpoints.tools import router as tools_router
from voice_api.api.v1.endpoints.workspace import router as workspace_router

__all__ = [
    "agents_router",
    "analysis_router",
    "artifacts_router",
    "browser_sessions_router",
    "callbacks_router",
    "calls_router",
    "contacts_router",
    "evidence_router",
    "execution_router",
    "integrations_router",
    "knowledge_router",
    "providers_router",
    "reconciliation_router",
    "runs_router",
    "telephony_router",
    "tools_router",
    "workspace_router",
]
