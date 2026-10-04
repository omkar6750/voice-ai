from collections.abc import AsyncIterator
from time import perf_counter

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from voice_runtime.perf_diagnostics import is_enabled, timing

from voice_api.core.config import get_settings
from voice_api.core.read_metrics import current, record
from voice_api.db import tenant_scope as _tenant_scope  # noqa: F401 - registers ORM guards

engine = create_async_engine(
    get_settings().database_url, pool_pre_ping=True, echo=False, hide_parameters=True
)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _query_started(_conn, _cursor, _statement, _parameters, _context, _executemany):
    if is_enabled():
        _context._voice_perf_started = perf_counter()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _query_finished(_conn, _cursor, _statement, _parameters, context, _executemany):
    started = getattr(context, "_voice_perf_started", None)
    if started is not None:
        elapsed_ms = (perf_counter() - started) * 1000
        record("db", elapsed_ms)
        if (metrics := current.get()) is not None and metrics.active:
            metrics.queries += 1
        if elapsed_ms >= 20:
            timing("db", "query", elapsed_ms)


class MeasuredSession(AsyncSession):
    async def _measure_acquisition(self):
        if (metrics := current.get()) is not None and metrics.active and not self.in_transaction():
            started = perf_counter()
            await self.connection()
            record("pool", (perf_counter() - started) * 1000)

    async def execute(self, *args, **kwargs):
        await self._measure_acquisition()
        return await super().execute(*args, **kwargs)

    async def scalar(self, *args, **kwargs):
        await self._measure_acquisition()
        return await super().scalar(*args, **kwargs)


SessionFactory = async_sessionmaker(engine, class_=MeasuredSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
