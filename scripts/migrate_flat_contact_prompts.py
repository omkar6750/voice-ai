"""Translate local drafts to flat variables; never mutate published records."""

import asyncio
import json

from sqlalchemy import text
from sqlalchemy.engine import make_url
from voice_api.core.config import get_settings
from voice_api.db.session import SessionFactory, engine
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import AgentVersion
from voice_api.services.resolution_service import resolve
from voice_runtime.contracts import AgentConfig
from voice_shared.contact_variables import normalize_contact_config


async def main():
    url = make_url(get_settings().database_url)
    if (url.host, url.port, url.database) != ("localhost", 55432, "voice"):
        raise RuntimeError("This updater only supports the local development database")
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text("select id, org_id from agent_versions where status='draft'")
            )
        ).all()
    changed = []
    for version_id, org_id in rows:
        async with SessionFactory() as session:
            bind_organization(session.sync_session, org_id)
            version = await session.get(AgentVersion, version_id, with_for_update=True)
            config = normalize_contact_config(version.config)
            if config == version.config:
                continue
            AgentConfig.model_validate(config)
            version.config = config
            version.revision += 1
            await resolve(session, version)
            await session.commit()
            changed.append({"id": version.id, "revision": version.revision})
    print(json.dumps({"updated_drafts": changed}))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
