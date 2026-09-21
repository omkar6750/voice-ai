from voice_runtime.config import default_agent_config


def test_default_agent_config_has_initial_tools() -> None:
    config = default_agent_config()

    assert config.name == "sales-qualifier"
    assert [tool.name for tool in config.tools] == [
        "classify_lead",
        "send_whatsapp",
        "schedule_callback",
    ]
