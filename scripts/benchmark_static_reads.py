"""Benchmark synthetic static reads only in the dedicated test DB; roll back all rows."""

import asyncio
import json
import os
from time import perf_counter

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from voice_runtime.safe_logs import configure_safe_logging

configure_safe_logging()

from voice_api.api.v1.endpoints.runs import list_runs  # noqa: E402
from voice_api.db.tenant_scope import bind_organization  # noqa: E402
from voice_api.models import Agent, AgentVersion, LegacyDataTenant, Run  # noqa: E402
from voice_api.models.common import new_id  # noqa: E402
from voice_api.schemas.run_reads import RunPageResponse  # noqa: E402


async def main():
    url = os.environ["VOICE_TEST_DATABASE_URL"]
    if not (make_url(url).database or "").endswith(("static_reads_test", "runtime_split_test")):
        raise SystemExit("Use a dedicated static_reads_test or runtime_split_test database only")
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    org_id = await session.scalar(select(LegacyDataTenant.organization_id))
                    bind_organization(session.sync_session, org_id)
                    agent_id, version_id = new_id(), new_id()
                    session.add(Agent(id=agent_id, name=agent_id))
                    await session.flush()
                    session.add(
                        AgentVersion(id=version_id, agent_id=agent_id, version=1, config={})
                    )
                    await session.flush()
                    for count in (58, 10_000):
                        await connection.execute(
                            text("""
                            INSERT INTO runs(id,org_id,agent_version_id,channel,status,resolved_config,contact_snapshot,created_at)
                            SELECT md5(:version || ':' || n::text), :org_id, :version, 'browser', 'failed',
                                jsonb_build_object('system_prompt', repeat('synthetic prompt ', 1200)),
                                '{"name":"Synthetic"}'::jsonb, now() - n * interval '1 second'
                            FROM generate_series(1, :count) AS n ON CONFLICT (id) DO NOTHING
                        """),
                            {"org_id": org_id, "version": version_id, "count": count},
                        )
                        await session.flush()
                        await connection.execute(text("ANALYZE runs"))
                        samples = []
                        size = 0
                        for _ in range(30):
                            started = perf_counter()
                            page = await list_runs(session=session, _=None)
                            encoded = RunPageResponse.model_validate(page).model_dump_json()
                            samples.append((perf_counter() - started) * 1000)
                            size = len(encoded.encode())
                        samples.sort()
                        print(
                            json.dumps(
                                {
                                    "synthetic_rows": count,
                                    "page_rows": len(page["runs"]),
                                    "route_and_serialization_p95_ms": round(samples[28], 2),
                                    "response_bytes": size,
                                }
                            )
                        )
                        if count == 58:
                            started = perf_counter()
                            rows = (
                                await session.scalars(select(Run).order_by(Run.created_at.desc()))
                            ).all()
                            print(
                                json.dumps(
                                    {
                                        "legacy_full_snapshot_read_ms": round(
                                            (perf_counter() - started) * 1000, 2
                                        ),
                                        "snapshot_json_bytes": sum(
                                            len(json.dumps(row.resolved_config).encode())
                                            for row in rows
                                        ),
                                    }
                                )
                            )
                        plan = await connection.execute(
                            text("""EXPLAIN (ANALYZE, BUFFERS)
                            SELECT id,created_at FROM runs WHERE org_id=:org_id
                            ORDER BY created_at DESC,id DESC LIMIT 26
                        """),
                            {"org_id": org_id},
                        )
                        # Remove tenant predicate lines: only access method and timings are reported.
                        for line in plan.scalars():
                            if (
                                "Index Scan" in line
                                or "Execution Time:" in line
                                or "Sort Method:" in line
                            ):
                                print(line.strip())
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
