from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from voice_api.core.config import get_settings
from voice_api.db import tenant_scope as _tenant_scope  # noqa: F401 - registers ORM guards

engine = create_async_engine(
    get_settings().database_url, pool_pre_ping=True, echo=False, hide_parameters=True
)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
