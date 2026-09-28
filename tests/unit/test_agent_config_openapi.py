from voice_api.main import app


def test_agent_revision_openapi_uses_runtime_config_schema():
    schemas = app.openapi()["components"]["schemas"]

    assert schemas["CreateBody"]["properties"]["config"]["$ref"] == (
        "#/components/schemas/AgentConfig"
    )
    assert schemas["RevisionBody"]["properties"]["config"]["$ref"] == (
        "#/components/schemas/AgentConfig"
    )
    assert schemas["AgentVersionResponse"]["properties"]["config"]["$ref"] == (
        "#/components/schemas/AgentConfig"
    )
