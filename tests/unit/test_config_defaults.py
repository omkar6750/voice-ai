from voice_api.core.config import Settings


def test_local_clerk_authorized_parties_include_script_dashboard_port() -> None:
    parties = Settings(_env_file=None).clerk_authorized_parties.split(",")

    assert "http://localhost:5174" in parties
