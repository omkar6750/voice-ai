from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from voice_api.core.config import Settings
from voice_api.core.security import require_legacy_owner
from voice_api.main import app


@pytest.fixture(autouse=True)
def allow_legacy_owner_for_legacy_api_tests():
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[require_legacy_owner] = lambda: None
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voice-api"}


@pytest.mark.asyncio
async def test_dashboard_is_not_served_by_the_api() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/agents/example/versions/example")
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")
    assert not any(getattr(route, "path", None) == "/" for route in app.routes)


@pytest.mark.asyncio
async def test_providers_and_config_schema_routes(monkeypatch) -> None:
    monkeypatch.setattr("voice_api.core.security.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("voice_api.api.deps.get_settings", lambda: Settings(_env_file=None))
    headers = {"Authorization": "Bearer test-token"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Test backward-compatible /api prefix
        monkeypatch.setattr(
            "voice_api.api.v1.endpoints.providers.required_organization", lambda _: "org_a"
        )
        monkeypatch.setattr(
            "voice_api.api.v1.endpoints.providers.settings_for_organization",
            AsyncMock(side_effect=lambda _session, _org_id, settings: settings),
        )
        monkeypatch.setattr(
            "voice_api.api.v1.endpoints.providers.get_provider_registry",
            AsyncMock(return_value={"providers": []}),
        )
        res1 = await client.get("/api/providers", headers=headers)
        assert res1.status_code == 200
        assert "providers" in res1.json()

        # Test standardized /api/v1 prefix
        res2 = await client.get("/api/v1/providers", headers=headers)
        assert res2.status_code == 200
        assert res2.json() == res1.json()

        # Test config-schema routes
        res_schema1 = await client.get("/api/config-schema", headers=headers)
        res_schema2 = await client.get("/api/v1/config-schema", headers=headers)
        assert res_schema1.status_code == 200
        assert res_schema2.status_code == 200
        assert "agent" in res_schema1.json()

        # Test tool handlers catalog
        res_handlers = await client.get("/api/v1/tools/handlers", headers=headers)
        assert res_handlers.status_code == 200
        handlers_data = res_handlers.json()
        assert "handlers" in handlers_data
        assert "http_policy" in handlers_data
        handler_names = {h["name"] for h in handlers_data["handlers"]}
        assert "change_node" in handler_names
        assert "end_call" in handler_names
        assert "send_whatsapp_template" in handler_names
        assert "send_whatsapp_message" in handler_names
        assert "check_whatsapp_window" in handler_names
        assert "classify_lead" in handler_names
        assert "classify_jev" not in handler_names
        assert "classify_llm" not in handler_names
        assert handlers_data["http_policy"]["follow_redirects"] is False


def test_contact_and_integration_patch_schemas() -> None:
    from voice_api.schemas.contact import ContactPatchBody
    from voice_api.schemas.integrations import UpdateConnectionBody, WhatsAppConfig

    # Valid contact patch
    patch = ContactPatchBody(name="Alice", phone_number="+15551234567", timezone="America/New_York")
    assert patch.phone_number == "+15551234567"
    assert patch.timezone == "America/New_York"

    # Invalid contact phone
    with pytest.raises(ValueError, match="international phone number"):
        ContactPatchBody(phone_number="12345")

    # Invalid contact timezone
    with pytest.raises(ValueError, match="valid IANA timezone"):
        ContactPatchBody(timezone="Invalid/Zone_Name")

    # Valid connection update
    conn_update = UpdateConnectionBody(
        label="Main WhatsApp",
        enabled=True,
        config=WhatsAppConfig(
            phone_number_id="123456789",
            waba_id="987654321",
            api_version="v23.0",
        ),
    )
    assert conn_update.label == "Main WhatsApp"
    assert conn_update.config.phone_number_id == "123456789"

    from voice_api.schemas.integrations import GenerateTemplateToolBody

    gen_body = GenerateTemplateToolBody(
        template_name="order_confirmation",
        language="en_US",
        tool_name="whatsapp_template_order_confirmation",
    )
    assert gen_body.template_name == "order_confirmation"
    assert gen_body.tool_name == "whatsapp_template_order_confirmation"


@pytest.mark.asyncio
async def test_config_schema():
    from voice_api.api.v1.endpoints.providers import config_schema

    schema = await config_schema()
    assert "agent" in schema
    assert "tool" in schema
    assert "workspace" in schema
    assert "runtime_application" in schema
    assert schema["runtime_application"]["flow"] == "applied"
    assert schema["runtime_application"]["classifier"] == "pending_runner"


def test_classifier_contracts_and_trimmer():
    from voice_runtime.contracts.cadence import ClassifierConfig, JevClassifierConfig, JevQuestion
    from voice_runtime.execution.native import trim_classifier_result

    # Test default LLM classifier
    cfg_llm = ClassifierConfig(
        classifier_type="llm", llm={"prompt": "Test prompt", "provider": "groq"}
    )
    assert cfg_llm.classifier_type == "llm"
    assert cfg_llm.llm.prompt == "Test prompt"
    assert cfg_llm.jev is None

    # Test Jev classifier
    cfg_jev = ClassifierConfig(
        classifier_type="jev",
        jev=JevClassifierConfig(
            model="jev-v2",
            questions={
                "custom_q": JevQuestion(
                    instructions="Custom question instructions",
                    criteria={"yes": "Customer said yes", "no": "Customer said no"},
                )
            },
        ),
    )
    assert cfg_jev.classifier_type == "jev"
    assert cfg_jev.llm is None
    assert cfg_jev.jev.model == "jev-v2"
    assert "custom_q" in cfg_jev.jev.questions
    assert cfg_jev.jev.questions["custom_q"].criteria["yes"] == "Customer said yes"

    # Test compact trimmer
    raw_res = {
        "lead_temperature": {
            "choice": "hot",
            "probabilities": {"hot": 0.85, "warm": 0.12, "cold": 0.03},
            "confidence": 0.85,
        },
        "service_fit": {"choice": "strong_fit", "confidence": 0.9},
        "notes": "Fast caller",
    }
    trimmed = trim_classifier_result(raw_res)
    assert trimmed["lead_temperature"] == "hot"
    assert "lead_temperature_hot" not in trimmed
    assert trimmed["service_fit"] == "strong_fit"
    assert "notes" not in trimmed


@pytest.mark.asyncio
async def test_contacts_variables_endpoint(monkeypatch) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from voice_api.api.deps import get_session

    monkeypatch.setattr("voice_api.core.security.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("voice_api.api.deps.get_settings", lambda: Settings(_env_file=None))

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("campaign",), ("ad_headline",)]
    mock_session.execute.return_value = mock_result

    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        headers = {"Authorization": "Bearer test-token"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/contacts/variables", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "columns" in data
        assert "metadata_keys" in data
        assert "temporal" in data

        # Check introspected columns
        col_keys = [c["key"] for c in data["columns"]]
        assert "name" in col_keys
        assert "business" in col_keys
        assert "source" in col_keys
        assert "language" in col_keys
        assert "timezone" in col_keys
        # Verify blocked columns are NOT exposed
        assert "id" not in col_keys
        assert "phone_number" not in col_keys
        assert "metadata_json" not in col_keys
        assert "created_at" not in col_keys

        # Check metadata keys
        meta_keys = [m["key"] for m in data["metadata_keys"]]
        assert "campaign" in meta_keys
        assert "ad_headline" in meta_keys

        # Check temporal keys
        temp_keys = [t["key"] for t in data["temporal"]]
        assert "greeting_phrase" in temp_keys
        assert "local_time_12h" in temp_keys
        assert "local_time_24h" in temp_keys
        assert "country" in temp_keys
        assert "country_code" in temp_keys
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_create_and_patch_contact_with_metadata(monkeypatch) -> None:
    from voice_api.api.deps import get_session
    from voice_api.models.configuration import Contact

    monkeypatch.setattr("voice_api.core.security.get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr("voice_api.api.deps.get_settings", lambda: Settings(_env_file=None))

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    # Test creating contact with custom metadata_json
    app.dependency_overrides[get_session] = lambda: mock_session
    try:
        headers = {"Authorization": "Bearer test-token"}
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/contacts",
                headers=headers,
                json={
                    "name": "Alex Rivera",
                    "phone_number": "+15551234567",
                    "timezone": "America/New_York",
                    "business": "Apex Growth",
                    "source": "meta_lead_ad",
                    "metadata_json": {
                        "campaign": "summer_scale_2026",
                        "budget": "10000",
                        "ad_id": "meta-ad-9988",
                    },
                },
            )
        assert res.status_code == 201
        assert "id" in res.json()
        added_contact = mock_session.add.call_args[0][0]
        assert isinstance(added_contact, Contact)
        assert added_contact.metadata_json == {
            "campaign": "summer_scale_2026",
            "budget": "10000",
            "ad_id": "meta-ad-9988",
        }

        # Test patching contact metadata_json
        existing_contact = Contact(
            id="c-test-id",
            name="Alex Rivera",
            phone_number="+15551234567",
            metadata_json={"campaign": "old_campaign"},
        )
        mock_session.get.return_value = existing_contact
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            patch_res = await client.patch(
                "/api/v1/contacts/c-test-id",
                headers=headers,
                json={
                    "metadata_json": {
                        "campaign": "updated_campaign_q4",
                        "ad_headline": "Free Consultation",
                    }
                },
            )
        assert patch_res.status_code == 200
        assert existing_contact.metadata_json == {
            "campaign": "updated_campaign_q4",
            "ad_headline": "Free Consultation",
        }
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_flow_node_config_allows_role_prompt_and_context_strategy() -> None:
    from voice_runtime.contracts.agent import FlowNodeConfig

    node = FlowNodeConfig(
        id="greeting",
        prompt="Hello!",
        role_prompt="You are a helpful assistant.",
        context_strategy="reset",
        terminal=True,
    )
    assert node.role_prompt == "You are a helpful assistant."
    assert node.context_strategy == "reset"


def test_verbatim_opening_requires_initial_node_to_wait() -> None:
    from pydantic import ValidationError
    from voice_runtime.contracts.agent import AgentConfig

    config = {
        "name": "opening-test",
        "greeting": "Hello {{name}}",
        "flow": {
            "initial_node": "greeting",
            "nodes": [
                {"id": "greeting", "prompt": "Continue after the caller answers", "terminal": True}
            ],
        },
    }
    with pytest.raises(ValidationError, match="verbatim opening"):
        AgentConfig.model_validate(config)


def test_legacy_persona_is_ignored_and_empty_greeting_keeps_immediate_default() -> None:
    from voice_runtime.contracts.agent import AgentConfig

    config = AgentConfig.model_validate(
        {
            "name": "legacy-agent",
            "persona": "legacy value",
            "flow": {
                "initial_node": "greeting",
                "nodes": [{"id": "greeting", "prompt": "Say hello", "terminal": True}],
            },
        }
    )
    assert config.flow.nodes[0].respond_immediately is True
    assert "persona" not in config.model_dump()
