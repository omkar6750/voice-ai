"""MCP capabilities remain subordinate to current organization membership."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from voice_api.core.clerk_auth import ClerkPrincipal
from voice_api.core.clerk_organizations import get_clerk_organization_directory
from voice_api.core.config import get_settings
from voice_api.core.security import allow_organization_member, require_organization_access
from voice_api.db.session import SessionFactory
from voice_api.models import Organization, User
from voice_api.models.mcp import McpAudit, McpRateBucket, McpToken


def environment() -> str:
    return "dev" if get_settings().env.casefold() in {"dev", "development", "local"} else "prod"


def connection_info(org_id: str) -> dict:
    settings = get_settings()
    base = settings.mcp_local_base_url if environment() == "dev" else settings.mcp_public_base_url
    parsed = urlsplit(base or "")
    valid = parsed.scheme == "https" or (
        environment() == "dev"
        and parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if (
        not valid
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise HTTPException(503, "Configure a valid environment-specific MCP base URL")
    suffix = sha256(org_id.encode()).hexdigest()[:10]
    env_var = f"VOICE_MCP_TOKEN_{suffix.upper()}_{environment().upper()}"
    url = base.rstrip("/") + "/mcp"
    command = f'codex mcp add voice-ai-{suffix}-{environment()} --url "{url}" --bearer-token-env-var {env_var}'
    return {"url": url, "environment": environment(), "env_var": env_var, "command": command}


async def limit(session, key: str, seconds: int, maximum: int) -> None:
    window = int(datetime.now(UTC).timestamp()) // seconds
    stmt = insert(McpRateBucket).values(key=key, window=window, count=1)
    count = await session.scalar(
        stmt.on_conflict_do_update(
            index_elements=[McpRateBucket.key, McpRateBucket.window],
            set_={"count": McpRateBucket.count + 1},
        ).returning(McpRateBucket.count)
    )
    await session.execute(
        delete(McpRateBucket).where(McpRateBucket.key == key, McpRateBucket.window < window - 2)
    )
    await session.commit()
    if count > maximum:
        raise HTTPException(
            429, "MCP request limit exceeded", headers={"Retry-After": str(seconds)}
        )


@dataclass(frozen=True)
class McpActor:
    principal: ClerkPrincipal
    user_id: str
    organization_id: str
    token_id: str


@allow_organization_member
def member_endpoint():
    """Authentication establishes membership; dispatch checks the target capability."""


async def authenticate(raw: str, *, consume_limit: bool = True) -> McpActor:
    if not raw.startswith("vmcp_") or len(raw) > 128:
        raise HTTPException(401, "Invalid MCP token")
    async with SessionFactory() as session:
        row = await session.scalar(
            select(McpToken).where(McpToken.token_hash == sha256(raw.encode()).hexdigest())
        )
        now = datetime.now(UTC)
        if (
            row is None
            or row.revoked_at
            or row.expires_at <= now
            or row.environment != environment()
        ):
            raise HTTPException(401, "Invalid or expired MCP token")
        user = await session.get(User, row.user_id)
        org = await session.get(Organization, row.organization_id)
        if user is None or user.disabled_at or org is None:
            raise HTTPException(403, "MCP account access unavailable")
        principal = ClerkPrincipal(user_id=user.clerk_user_id, org_id=org.clerk_org_id)
        actor = McpActor(principal, user.id, org.id, row.id)
        request = Request(
            {
                "type": "http",
                "headers": [],
                "route": type("Route", (), {"endpoint": staticmethod(member_endpoint)})(),
            }
        )
        principal = await require_organization_access(
            request, principal, session, get_clerk_organization_directory()
        )
        if consume_limit:
            await limit(session, f"token:{actor.token_id}", 60, 120)
        await session.execute(
            update(McpToken).where(McpToken.id == actor.token_id).values(last_used_at=now)
        )
        await session.commit()
        return McpActor(principal, actor.user_id, actor.organization_id, actor.token_id)


async def issue(
    session, user: User, org: Organization, name: str, days: int
) -> tuple[McpToken, str]:
    await limit(session, f"create:{user.id}", 3600, 20)
    raw = "vmcp_" + token_urlsafe(32)
    row = McpToken(
        token_hash=sha256(raw.encode()).hexdigest(),
        user_id=user.id,
        organization_id=org.id,
        name=name,
        environment=environment(),
        expires_at=datetime.now(UTC) + timedelta(days=days),
    )
    session.add(row)
    await session.flush()
    session.add(
        McpAudit(
            organization_id=org.id,
            actor_user_id=user.id,
            token_id=row.id,
            operation="token.create",
            outcome="success",
            targets={},
        )
    )
    await session.commit()
    return row, raw
