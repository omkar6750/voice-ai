from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from voice_api.api.v1.endpoints.agents import delete_agent
from voice_api.api.v1.endpoints.integrations import delete_connection
from voice_api.api.v1.endpoints.tools import delete_tool
from voice_api.core.development import require_development_cleanup


@pytest.mark.parametrize("environment", ["production", "staging", "test", "", "DEV"])
def test_cleanup_requires_explicit_development(monkeypatch, environment):
    monkeypatch.setattr(
        "voice_api.core.development.get_settings", lambda: SimpleNamespace(env=environment)
    )
    with pytest.raises(HTTPException) as error:
        require_development_cleanup()
    assert error.value.status_code == 403


def test_cleanup_preserves_local_development(monkeypatch):
    monkeypatch.setattr(
        "voice_api.core.development.get_settings", lambda: SimpleNamespace(env="dev")
    )
    require_development_cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", [delete_agent, delete_tool, delete_connection])
async def test_hosted_delete_never_reads_or_disables_triggers(monkeypatch, endpoint):
    monkeypatch.setattr(
        "voice_api.core.development.get_settings", lambda: SimpleNamespace(env="production")
    )
    session = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await endpoint("opaque-id", session=session, _=None)
    assert error.value.status_code == 403
    session.get.assert_not_called()
    session.execute.assert_not_called()
