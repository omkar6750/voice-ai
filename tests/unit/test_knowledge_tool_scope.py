"""A KB tool cannot silently search another attached base or the global database."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from voice_api.db import tenant_scope
from voice_api.services import knowledge_service
from voice_runtime.contracts.tools import ToolConfig
from voice_runtime.execution.native import NativePipelineHost


@pytest.mark.parametrize("base_id", [None, "other-base"])
async def test_knowledge_tool_without_attached_identity_fails_closed(base_id):
    host = NativePipelineHost("test-run", Path("unused"), SimpleNamespace())
    host._snapshot = {
        "_resolved": {
            "knowledge": [{"id": "attached-base"}],
            "tools": {
                "product_facts": {
                    "definition": {
                        "handler": "query_knowledge_base",
                        "knowledge_base_id": base_id,
                    }
                }
            },
        }
    }

    result = await host._handler("product_facts")({"query": "price"}, None)

    assert result == {
        "status": "error",
        "error": "Knowledge tool is not scoped to an attached knowledge base",
    }


def test_knowledge_identity_is_part_of_the_versioned_tool_definition():
    tool = ToolConfig.model_validate(
        {
            "name": "product_facts",
            "handler": "query_knowledge_base",
            "knowledge_base_id": "attached-base",
        }
    )
    assert tool.model_dump(exclude_none=True)["knowledge_base_id"] == "attached-base"


async def test_single_base_tool_queries_only_its_bound_base(monkeypatch):
    host = NativePipelineHost(
        "test-run", Path("unused"), SimpleNamespace(gemini_api_key=None)
    )
    host._snapshot = {
        "_resolved": {
            "knowledge": [{"id": "base-a"}, {"id": "base-b"}],
            "tools": {
                "product_facts": {
                    "definition": {
                        "handler": "query_knowledge_base",
                        "knowledge_base_id": "base-a",
                    }
                }
            },
        }
    }
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(knowledge_service, "search", search)
    monkeypatch.setattr(
        tenant_scope, "bind_run_organization", AsyncMock(return_value="org-test")
    )

    result = await host._handler("product_facts")({"query": "price"}, None)

    assert result["status"] == "not_found"
    search.assert_awaited_once()
    assert search.await_args.args[1] == "base-a"
