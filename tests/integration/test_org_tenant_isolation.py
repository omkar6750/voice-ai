"""Prove PostgreSQL prevents a tenant from reading or referencing another org."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.core.clerk_auth import ClerkPrincipal
from voice_api.core.clerk_organizations import OrganizationMember
from voice_api.core.security import require_organization_access
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import (
    Agent,
    AgentVersion,
    LegacyDataTenant,
    Organization,
    PlatformAdministrator,
    PlatformSupportSession,
    User,
)
from voice_api.models.common import new_id


@pytest.mark.asyncio
async def test_postgres_blocks_cross_organization_reads_writes_and_references(database):
    original_org_id = await database.scalar(select(LegacyDataTenant.organization_id))
    assert original_org_id

    user_id = new_id()
    clerk_user_id = f"user_tenant_test_{user_id}"
    second_org_id = new_id()
    second_agent_id = new_id()
    database.add(User(id=user_id, clerk_user_id=f"user_tenant_test_{user_id}"))
    await database.flush()
    database.add(
        Organization(
            id=second_org_id,
            clerk_org_id=f"org_tenant_test_{second_org_id}",
            name="Tenant isolation test",
            owner_user_id=user_id,
        )
    )
    await database.flush()

    connection = await database.connection()
    async with AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as second_org_session:
        bind_organization(second_org_session.sync_session, second_org_id)
        second_org_session.add(
            Agent(id=second_agent_id, org_id=second_org_id, name="Private second-org agent")
        )
        await second_org_session.commit()

    # The user-facing gate verifies live membership and binds the registered org.
    async with AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as member_session:

        class Directory:
            async def membership(self, org_id, user_id):
                assert org_id == f"org_tenant_test_{second_org_id}"
                assert user_id == clerk_user_id
                return OrganizationMember(user_id, "org:member", None, None, None)

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/agents",
                "headers": [],
                "route": SimpleNamespace(
                    endpoint=SimpleNamespace(__allow_organization_member__=True)
                ),
            }
        )
        principal = await require_organization_access(
            request,
            ClerkPrincipal(clerk_user_id, f"org_tenant_test_{second_org_id}"),
            member_session,
            Directory(),
        )
        assert principal.user_id == clerk_user_id
        assert member_session.sync_session.info["organization_scope_id"] == second_org_id
        assert (
            await member_session.scalar(select(Agent.id).where(Agent.id == second_agent_id))
            == second_agent_id
        )

    # The request session remains bound to the original org; both ORM identity
    # lookups and Core reads must hide the other org, and bulk mutation must
    # affect zero rows.
    assert await database.get(Agent, second_agent_id) is None
    assert await database.scalar(select(Agent.name).where(Agent.id == second_agent_id)) is None
    assert (
        await database.scalar(
            select(Agent.__table__.c.id).where(Agent.__table__.c.id == second_agent_id)
        )
        is None
    )
    result = await database.execute(
        update(Agent).where(Agent.id == second_agent_id).values(name="stolen")
    )
    assert result.rowcount == 0

    # ORM scope stamps the attempted child with original_org_id. The DB trigger
    # installed by migration 0033 must reject its FK to the second-org agent.
    with pytest.raises(IntegrityError, match="cross-organization reference"):
        async with database.begin_nested():
            database.add(
                AgentVersion(
                    id=new_id(),
                    org_id=original_org_id,
                    agent_id=second_agent_id,
                    version=1,
                    revision=1,
                    status="draft",
                    config={"name": "cross-org-reference"},
                )
            )
            await database.flush()


@pytest.mark.asyncio
async def test_postgres_platform_support_session_binds_assigned_admin_to_target_org(database):
    connection = await database.connection()
    user = (
        await database.execute(
            select(User).join(PlatformAdministrator, PlatformAdministrator.user_id == User.id)
        )
    ).scalar_one()
    organization_id = await database.scalar(select(LegacyDataTenant.organization_id))
    organization = await database.get(Organization, organization_id)
    token = "integration-support-session-secret"

    async with AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    ) as session:
        session.add(
            PlatformSupportSession(
                token_hash=sha256(token.encode()).hexdigest(),
                user_id=user.id,
                organization_id=organization_id,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await session.flush()
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/agents",
                "headers": [(b"x-platform-support-session", token.encode())],
                "route": SimpleNamespace(endpoint=SimpleNamespace()),
            }
        )
        principal = await require_organization_access(
            request,
            ClerkPrincipal(user.clerk_user_id, None),
            session,
            object(),
        )
        assert principal.org_id == organization.clerk_org_id
        assert session.sync_session.info["organization_scope_id"] == organization_id
