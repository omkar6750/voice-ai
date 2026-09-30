"""Request-local ORM guard for organization-owned records.

Tenant ORM reads and writes fail closed without a bound organization. Raw SQL
still requires an explicit predicate and a verified request/run scope.
"""

import re

from fastapi import HTTPException
from sqlalchemy import bindparam, event, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, with_loader_criteria
from sqlalchemy.sql import operators, visitors
from sqlalchemy.sql.elements import BindParameter, TextClause
from sqlalchemy.sql.schema import Table

from voice_api.models.common import Base, OrganizationOwned

_SCOPE_KEY = "organization_scope_id"
_SCOPE_BOOTSTRAP = "_scope_bootstrap"
_PLATFORM_ADMIN_SCOPE = "platform_admin_scope"
_PLATFORM_ADMIN_READ = "_platform_admin_read"


def _references_tenant_table(statement) -> bool:
    tenant_tables = {table.name for table in _tenant_tables()}
    if isinstance(statement, TextClause):
        sql = str(statement).lower()
        return any(re.search(rf"\b{re.escape(name.lower())}\b", sql) for name in tenant_tables)
    return any(
        isinstance(element, Table) and element.name in tenant_tables
        for element in visitors.iterate(statement)
    )


def _tenant_tables() -> tuple[Table, ...]:
    return tuple(table for table in Base.metadata.tables.values() if "org_id" in table.c)


def _has_explicit_text_scope(statement, parameters, organization_id: str) -> bool:
    """Require hand-written tenant SQL to pass the matching org predicate."""
    if not isinstance(statement, TextClause):
        return False
    sql = str(statement)
    if not re.search(r"\borg_id\s*=\s*:org_id\b", sql, re.IGNORECASE):
        return False
    if isinstance(parameters, dict):
        return parameters.get("org_id") == organization_id
    if isinstance(parameters, (list, tuple)):
        return bool(parameters) and all(
            isinstance(item, dict) and item.get("org_id") == organization_id for item in parameters
        )
    return False


def _scope_single_table_text(statement, parameters, organization_id: str):
    """Add the bound tenant predicate to unambiguous single-table raw SQL."""
    sql = str(statement)
    tenant_names = [
        table.name
        for table in _tenant_tables()
        if re.search(rf"\b{re.escape(table.name)}\b", sql, re.IGNORECASE)
    ]
    if len(tenant_names) != 1 or len(re.findall(r"\bWHERE\b", sql, re.IGNORECASE)) != 1:
        return None
    table_name = tenant_names[0]
    # Aliases make a safely qualified predicate ambiguous; callers must then
    # provide an explicit predicate for every participating tenant table.
    alias = re.search(
        rf"\b(?:FROM|UPDATE|INTO)\s+{re.escape(table_name)}\s+(?:AS\s+)?([a-z_]\w*)",
        sql,
        re.IGNORECASE,
    )
    if alias and alias.group(1).lower() not in {
        "where",
        "set",
        "values",
        "returning",
    }:
        return None
    match = re.search(
        r"\bWHERE\b(.*?)(\s+(?:ORDER\s+BY|GROUP\s+BY|LIMIT|RETURNING|FOR\s+UPDATE)\b.*|;?\s*)$",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    if match is None or not match.group(1).strip():
        return None
    scoped = (
        sql[: match.start(1)]
        + " ("
        + match.group(1).strip()
        + f") AND {table_name}.org_id = :_tenant_scope_org_id"
        + match.group(2)
    )
    bound = dict(parameters) if isinstance(parameters, dict) else {}
    return text(scoped).bindparams(bindparam("_tenant_scope_org_id", value=organization_id)), bound


def bind_organization(session: Session, organization_id: str) -> None:
    """Bind exactly one verified local org to a request's database session."""
    existing = session.info.get(_SCOPE_KEY)
    if existing is not None and existing != organization_id:
        raise HTTPException(403, "Organization context cannot change")
    for row in session.identity_map.values():
        if isinstance(row, OrganizationOwned) and row.org_id != organization_id:
            raise HTTPException(404, "Organization resource not found")
    session.info[_SCOPE_KEY] = organization_id


def mark_platform_admin(session: Session) -> None:
    """Mark a request session after the platform-admin assignment is verified."""
    session.info[_PLATFORM_ADMIN_SCOPE] = True


def platform_admin_read(statement):
    """Opt a specific read into the verified platform-admin aggregate path."""
    return statement.execution_options(**{_PLATFORM_ADMIN_READ: True})


def required_organization(session: Session) -> str:
    """Refuse tenant-owned raw SQL unless the caller has established a scope."""
    organization_id = session.info.get(_SCOPE_KEY)
    if not organization_id:
        raise HTTPException(403, "Organization context required")
    return organization_id


async def bind_run_organization(
    session: AsyncSession, run_id: str, *, expected_org_id: str | None = None
) -> str:
    """Derive a runtime session's tenant from the persisted run identity."""
    from voice_api.models import Run

    # This trusted runtime bootstrap reads only the run identity/scope columns
    # through Core; ORM access is denied until the verified scope is bound.
    result = await session.execute(
        select(Run.__table__.c.org_id)
        .where(Run.__table__.c.id == run_id)
        .execution_options(**{_SCOPE_BOOTSTRAP: True})
    )
    org_id = result.scalar_one_or_none()
    if not org_id or (expected_org_id and org_id != expected_org_id):
        raise HTTPException(404, "Run not found")
    bind_organization(session.sync_session, org_id)
    return org_id


async def bind_contact_organization(session: AsyncSession, contact_id: str) -> str:
    """Establish runtime callback scope from the contact's opaque primary key."""
    from voice_api.models import Contact

    result = await session.execute(
        select(Contact.__table__.c.org_id)
        .where(Contact.__table__.c.id == contact_id)
        .execution_options(**{_SCOPE_BOOTSTRAP: True})
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "Contact not found")
    bind_organization(session.sync_session, org_id)
    return org_id


async def bind_call_organization(session: AsyncSession, correlation_id: str) -> str:
    """Establish tenant scope from a unique callback correlation token."""
    from voice_api.models import Call

    result = await session.execute(
        select(Call.__table__.c.org_id)
        .where(Call.__table__.c.correlation_id == correlation_id)
        .execution_options(**{_SCOPE_BOOTSTRAP: True})
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "Call not found")
    bind_organization(session.sync_session, org_id)
    return org_id


async def bind_integration_organization(session: AsyncSession, connection_id: str) -> str:
    """Establish webhook scope from the opaque primary key of its connection."""
    from voice_api.models import IntegrationConnection

    result = await session.execute(
        select(IntegrationConnection.__table__.c.org_id)
        .where(IntegrationConnection.__table__.c.id == connection_id)
        .execution_options(**{_SCOPE_BOOTSTRAP: True})
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "Integration connection not found")
    bind_organization(session.sync_session, org_id)
    return org_id


async def bind_knowledge_source_organization(
    session: AsyncSession, source_id: str, *, missing_ok: bool = False
) -> str | None:
    """Establish background-ingestion scope from a source's opaque primary key."""
    from voice_api.models import KnowledgeSource

    result = await session.execute(
        select(KnowledgeSource.__table__.c.org_id)
        .where(KnowledgeSource.__table__.c.id == source_id)
        .execution_options(**{_SCOPE_BOOTSTRAP: True})
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        if missing_ok:
            return None
        raise HTTPException(404, "Knowledge source not found")
    bind_organization(session.sync_session, org_id)
    return org_id


async def bind_calendar_oauth_organization(session: AsyncSession, state_hash: str) -> str:
    """Bind OAuth callback scope using the unique, high-entropy state hash."""
    from voice_api.models import CalendarOAuthState

    result = await session.execute(
        select(CalendarOAuthState.__table__.c.org_id)
        .where(CalendarOAuthState.__table__.c.state_hash == state_hash)
        .execution_options(**{_SCOPE_BOOTSTRAP: True})
    )
    org_id = result.scalar_one_or_none()
    if not org_id:
        raise HTTPException(404, "OAuth state not found")
    bind_organization(session.sync_session, org_id)
    return org_id


def _valid_bootstrap_query(statement) -> bool:
    """Allow only scalar org lookups by opaque run/call/contact/integration/OAuth/source IDs."""
    if not getattr(statement, "is_select", False):
        return False
    froms = statement.get_final_froms()
    if len(froms) != 1 or not isinstance(froms[0], Table):
        return False
    table = froms[0]
    if table.name == "runs":
        key_column = table.c.id
    elif table.name == "calls":
        key_column = table.c.correlation_id
    elif table.name == "contacts":
        key_column = table.c.id
    elif table.name == "integration_connections":
        key_column = table.c.id
    elif table.name == "knowledge_sources":
        key_column = table.c.id
    elif table.name == "calendar_oauth_states":
        key_column = table.c.state_hash
    else:
        return False
    columns = tuple(statement.selected_columns)
    if len(columns) != 1 or columns[0] is not table.c.org_id:
        return False
    criteria = tuple(statement._where_criteria)
    if len(criteria) != 1:
        return False
    criterion = criteria[0]
    if (
        getattr(criterion, "operator", None) is not operators.eq
        or getattr(criterion, "left", None) is not key_column
        or not isinstance(getattr(criterion, "right", None), BindParameter)
    ):
        return False
    return True


@event.listens_for(Session, "do_orm_execute")
def _scope_orm_statements(state) -> None:
    org_id = state.session.info.get(_SCOPE_KEY)
    references_tenant = _references_tenant_table(state.statement)
    if state.execution_options.get(_PLATFORM_ADMIN_READ) and references_tenant:
        if not state.session.info.get(_PLATFORM_ADMIN_SCOPE) or not state.is_select:
            raise HTTPException(status_code=403, detail="Platform-admin read required")
        return
    tenant_mappers = tuple(
        mapper for mapper in state.all_mappers if issubclass(mapper.class_, OrganizationOwned)
    )
    if tenant_mappers and org_id is None:
        raise HTTPException(403, "Organization context required")
    scope_bootstrap = state.execution_options.get(_SCOPE_BOOTSTRAP)
    if references_tenant and scope_bootstrap:
        if not _valid_bootstrap_query(state.statement):
            raise HTTPException(403, "Invalid runtime scope bootstrap query")
    elif references_tenant and not tenant_mappers:
        if org_id is None:
            raise HTTPException(403, "Organization context required")
        if isinstance(state.statement, TextClause):
            update_set = re.search(
                r"\bUPDATE\b[\s\S]*?\bSET\b(.*?)(?:\bWHERE\b|$)",
                str(state.statement),
                re.IGNORECASE,
            )
            if update_set and re.search(
                r"(?<![\w.])(?:[a-z_]\w*\.)?\"?org_id\"?\s*=",
                update_set.group(1),
                re.IGNORECASE,
            ):
                raise HTTPException(403, "Organization ownership cannot change")
            if not _has_explicit_text_scope(state.statement, state.parameters, org_id):
                has_supplied_scope = re.search(
                    r"\borg_id\s*=\s*:org_id\b", str(state.statement), re.IGNORECASE
                )
                supplied_parameters = state.parameters
                if (
                    has_supplied_scope
                    and isinstance(supplied_parameters, dict)
                    and "org_id" in supplied_parameters
                ):
                    raise HTTPException(403, "Tenant SQL organization does not match session")
                rewritten = _scope_single_table_text(state.statement, state.parameters, org_id)
                if rewritten is None:
                    raise HTTPException(
                        403, "Tenant SQL requires an explicit organization predicate"
                    )
                state.statement, state.parameters = rewritten
        else:
            referenced_names = {
                element.name
                for element in visitors.iterate(state.statement)
                if isinstance(element, Table)
                and any(element.name == tenant.name for tenant in _tenant_tables())
            }
            if state.is_select and len(referenced_names) == 1:
                tenant_table = next(
                    table for table in _tenant_tables() if table.name in referenced_names
                )
                state.statement = state.statement.where(tenant_table.c.org_id == org_id)
            else:
                raise HTTPException(403, "Tenant Core query must use the scoped ORM")
    if references_tenant and org_id is None and not scope_bootstrap:
        raise HTTPException(403, "Organization context required")
    if tenant_mappers and state.is_insert:
        raise HTTPException(
            403, "Tenant-owned rows must be inserted through the scoped unit of work"
        )
    if org_id is None or not (state.is_select or state.is_update or state.is_delete):
        return
    if state.is_update and "org_id" in state.statement.compile().params:
        raise HTTPException(403, "Organization ownership cannot change")
    state.statement = state.statement.options(
        with_loader_criteria(
            OrganizationOwned,
            lambda model: model.org_id == org_id,
            include_aliases=True,
            propagate_to_loaders=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _guard_orm_writes(session, _flush_context, _instances) -> None:
    org_id = session.info.get(_SCOPE_KEY)
    tenant_rows = {
        row
        for row in session.new | session.dirty | session.deleted
        if isinstance(row, OrganizationOwned)
    }
    if tenant_rows and org_id is None:
        raise HTTPException(403, "Organization context required")
    if org_id is None:
        return
    for row in session.new:
        if not isinstance(row, OrganizationOwned):
            continue
        if row.org_id is None:
            row.org_id = org_id
        elif row.org_id != org_id:
            raise HTTPException(404, "Organization resource not found")
    for row in session.dirty | session.deleted:
        if not isinstance(row, OrganizationOwned):
            continue
        if row.org_id != org_id:
            raise HTTPException(404, "Organization resource not found")
        if inspect(row).attrs.org_id.history.has_changes():
            raise HTTPException(403, "Organization ownership cannot change")
