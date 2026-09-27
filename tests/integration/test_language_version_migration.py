"""The one-time migration removes dead language flags from all agent versions."""

from sqlalchemy import text


async def test_agent_version_language_flags_are_absent(database):
    remaining = await database.scalar(
        text(
            """
            SELECT count(*) FROM agent_versions
            WHERE config #> '{language,follow_caller_language}' IS NOT NULL
               OR config #> '{language,persist_requested_language}' IS NOT NULL
            """
        )
    )
    assert remaining == 0
