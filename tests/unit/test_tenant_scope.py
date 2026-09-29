"""The legacy gate's request session must not mix organization-owned ORM rows."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, func, insert, select, text, update
from sqlalchemy.orm import Session
from voice_api.db.tenant_scope import (
    _SCOPE_BOOTSTRAP,
    _valid_bootstrap_query,
    bind_calendar_oauth_organization,
    bind_call_organization,
    bind_integration_organization,
    bind_knowledge_source_organization,
    bind_organization,
    bind_run_organization,
)
from voice_api.models import (
    Agent,
    CalendarOAuthState,
    Call,
    IntegrationConnection,
    KnowledgeSource,
    Run,
)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE agents (id varchar(36) PRIMARY KEY, name varchar(120), "
                "created_at datetime, active_version_id varchar(36), "
                "archived_at datetime, org_id varchar(36))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO agents (id, name, org_id) VALUES "
                "('own', 'Visible', 'org_one'), ('foreign', 'Hidden', 'org_two')"
            )
        )
    return engine


def test_scoped_reads_hide_foreign_rows_including_primary_key_get() -> None:
    with Session(_engine()) as session:
        bind_organization(session, "org_one")
        assert [agent.id for agent in session.scalars(select(Agent)).all()] == ["own"]
        assert session.scalars(select(Agent.id)).all() == ["own"]
        assert session.scalar(select(func.count(Agent.id))) == 1
        assert session.get(Agent, "foreign") is None
        assert session.get(Agent, "own") is not None


def test_unscoped_tenant_orm_reads_and_bulk_writes_fail_closed() -> None:
    with Session(_engine()) as session:
        with pytest.raises(HTTPException, match="Organization context required"):
            session.scalars(select(Agent)).all()
        with pytest.raises(HTTPException, match="Organization context required"):
            session.scalars(select(Agent.id)).all()
        with pytest.raises(HTTPException, match="Organization context required"):
            session.scalar(select(func.count(Agent.id)))
        with pytest.raises(HTTPException, match="Organization context required"):
            session.get(Agent, "own")
        with pytest.raises(HTTPException, match="Organization context required"):
            session.execute(select(Agent.__table__.c.id))
        with pytest.raises(HTTPException, match="Organization context required"):
            session.execute(text("SELECT id FROM agents"))
        with pytest.raises(HTTPException, match="Organization context required"):
            session.execute(update(Agent).values(name="Changed"))
        with pytest.raises(HTTPException, match="Organization context required"):
            session.execute(delete(Agent))
        with pytest.raises(HTTPException, match="Organization context required"):
            session.execute(insert(Agent).values(id="bulk", name="Blocked", org_id="org_one"))


def test_scoped_core_and_text_tenant_queries_require_explicit_matching_scope() -> None:
    with Session(_engine()) as session:
        bind_organization(session, "org_one")
        assert session.execute(select(Agent.__table__.c.id)).scalars().all() == ["own"]
        assert session.scalar(select(func.count()).select_from(Agent.__table__)) == 1
        with pytest.raises(HTTPException, match="explicit organization predicate"):
            session.execute(text("SELECT id FROM agents"))
        with pytest.raises(HTTPException, match="does not match session"):
            session.execute(
                text("SELECT id FROM agents WHERE org_id = :org_id"),
                {"org_id": "org_two"},
            )

        rows = session.execute(
            text("SELECT id FROM agents WHERE org_id = :org_id"),
            {"org_id": "org_one"},
        ).scalars()
        assert rows.all() == ["own"]
        with pytest.raises(HTTPException, match="Organization ownership cannot change"):
            session.execute(
                text("UPDATE agents SET org_id = :target WHERE id = :id AND org_id = :org_id"),
                {"target": "org_two", "id": "own", "org_id": "org_one"},
            )


def test_unscoped_tenant_unit_of_work_writes_fail_closed() -> None:
    with Session(_engine()) as session:
        session.add(Agent(id="unscoped", name="Blocked"))
        with pytest.raises(HTTPException, match="Organization context required"):
            session.flush()


def test_scoped_orm_writes_stamp_org_and_reject_foreign_org() -> None:
    engine = _engine()
    with Session(engine) as session:
        bind_organization(session, "org_one")
        row = Agent(id="new", name="Created")
        session.add(row)
        session.flush()
        assert row.org_id == "org_one"
        session.rollback()
        session.add(Agent(id="wrong", name="Blocked", org_id="org_two"))
        with pytest.raises(HTTPException) as denied:
            session.flush()
        assert denied.value.status_code == 404


def test_request_scope_cannot_switch_organizations() -> None:
    with Session(_engine()) as session:
        bind_organization(session, "org_one")
        with pytest.raises(HTTPException) as denied:
            bind_organization(session, "org_two")
        assert denied.value.status_code == 403


def test_bulk_update_and_delete_touch_only_current_org() -> None:
    engine = _engine()
    with Session(engine) as session:
        bind_organization(session, "org_one")
        assert session.execute(update(Agent).values(name="Renamed")).rowcount == 1
        assert session.execute(delete(Agent)).rowcount == 1
        session.commit()
    with Session(engine) as session:
        bind_organization(session, "org_two")
        foreign = session.get(Agent, "foreign")
        assert foreign.name == "Hidden"


def test_scope_cannot_switch_after_loading_tenant_data() -> None:
    with Session(_engine()) as session:
        bind_organization(session, "org_two")
        foreign = session.get(Agent, "foreign")
        assert foreign is not None
        with pytest.raises(HTTPException) as denied:
            bind_organization(session, "org_one")
        assert denied.value.status_code == 403


def test_bulk_update_cannot_move_resources_to_another_org() -> None:
    with Session(_engine()) as session:
        bind_organization(session, "org_one")
        with pytest.raises(HTTPException) as denied:
            session.execute(update(Agent).values(org_id="org_two"))
        assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_runtime_scope_is_derived_from_persisted_run() -> None:
    with Session() as sync_session:
        session = SimpleNamespace(
            sync_session=sync_session,
            execute=AsyncMock(
                side_effect=[
                    SimpleNamespace(scalar_one_or_none=lambda: "org-one"),
                    SimpleNamespace(scalar_one_or_none=lambda: "org-one"),
                    SimpleNamespace(scalar_one_or_none=lambda: None),
                ]
            ),
        )
        assert await bind_run_organization(session, "run-one", expected_org_id="org-one") == (
            "org-one"
        )
        bootstrap_query = session.execute.await_args.args[0]
        assert bootstrap_query.get_execution_options()[_SCOPE_BOOTSTRAP] is True
        assert sync_session.info["organization_scope_id"] == "org-one"
        with pytest.raises(HTTPException) as denied:
            await bind_run_organization(session, "run-one", expected_org_id="org-two")
        assert denied.value.status_code == 404
        with pytest.raises(HTTPException) as missing:
            await bind_run_organization(session, "missing")
        assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_callback_scope_is_derived_from_unique_call_correlation_id() -> None:
    with Session() as sync_session:
        session = SimpleNamespace(
            sync_session=sync_session,
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "org-call")),
        )
        assert await bind_call_organization(session, "unguessable-correlation") == "org-call"
        query = session.execute.await_args.args[0]
        assert query.get_execution_options()[_SCOPE_BOOTSTRAP] is True
        assert tuple(query.selected_columns) == (Call.__table__.c.org_id,)
        assert sync_session.info["organization_scope_id"] == "org-call"


@pytest.mark.asyncio
async def test_webhook_scope_is_derived_from_integration_primary_key() -> None:
    with Session() as sync_session:
        session = SimpleNamespace(
            sync_session=sync_session,
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "org-hook")),
        )
        assert await bind_integration_organization(session, "opaque-connection-id") == "org-hook"
        query = session.execute.await_args.args[0]
        assert query.get_execution_options()[_SCOPE_BOOTSTRAP] is True
        assert tuple(query.selected_columns) == (IntegrationConnection.__table__.c.org_id,)
        assert sync_session.info["organization_scope_id"] == "org-hook"


@pytest.mark.asyncio
async def test_knowledge_build_scope_is_derived_from_source_primary_key() -> None:
    with Session() as sync_session:
        session = SimpleNamespace(
            sync_session=sync_session,
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "org-kb")),
        )
        assert await bind_knowledge_source_organization(session, "opaque-source-id") == "org-kb"
        query = session.execute.await_args.args[0]
        assert query.get_execution_options()[_SCOPE_BOOTSTRAP] is True
        assert tuple(query.selected_columns) == (KnowledgeSource.__table__.c.org_id,)
        assert sync_session.info["organization_scope_id"] == "org-kb"


@pytest.mark.asyncio
async def test_calendar_oauth_callback_scope_is_derived_from_state_hash() -> None:
    with Session() as sync_session:
        session = SimpleNamespace(
            sync_session=sync_session,
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "org-calendar")),
        )
        assert await bind_calendar_oauth_organization(session, "sha256-state-hash") == "org-calendar"
        query = session.execute.await_args.args[0]
        assert query.get_execution_options()[_SCOPE_BOOTSTRAP] is True
        assert tuple(query.selected_columns) == (CalendarOAuthState.__table__.c.org_id,)
        assert sync_session.info["organization_scope_id"] == "org-calendar"


def test_scope_bootstrap_accepts_only_narrow_org_lookups() -> None:
    run_lookup = select(Run.__table__.c.org_id).where(Run.__table__.c.id == "run-id")
    call_lookup = select(Call.__table__.c.org_id).where(
        Call.__table__.c.correlation_id == "correlation-id"
    )
    integration_lookup = select(IntegrationConnection.__table__.c.org_id).where(
        IntegrationConnection.__table__.c.id == "connection-id"
    )
    source_lookup = select(KnowledgeSource.__table__.c.org_id).where(
        KnowledgeSource.__table__.c.id == "source-id"
    )
    oauth_lookup = select(CalendarOAuthState.__table__.c.org_id).where(
        CalendarOAuthState.__table__.c.state_hash == "unique-state-hash"
    )
    assert _valid_bootstrap_query(run_lookup)
    assert _valid_bootstrap_query(call_lookup)
    assert _valid_bootstrap_query(integration_lookup)
    assert _valid_bootstrap_query(source_lookup)
    assert _valid_bootstrap_query(oauth_lookup)
    assert not _valid_bootstrap_query(select(Run.__table__))
    assert not _valid_bootstrap_query(
        select(Run.__table__.c.org_id, Run.__table__.c.id).where(Run.__table__.c.id == "run-id")
    )
    assert not _valid_bootstrap_query(
        select(Run.__table__.c.org_id).where(
            Run.__table__.c.id == "run-id", Run.__table__.c.status == "queued"
        )
    )
    assert not _valid_bootstrap_query(
        select(Call.__table__.c.org_id).where(Call.__table__.c.id == "call-id")
    )
    assert not _valid_bootstrap_query(
        select(IntegrationConnection.__table__.c.org_id).where(
            IntegrationConnection.__table__.c.provider == "whatsapp"
        )
    )
    assert not _valid_bootstrap_query(
        select(KnowledgeSource.__table__.c.org_id).where(KnowledgeSource.__table__.c.status == "ready")
    )
