"""Fetch and export any agent's draft, published, or specific version snapshot."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from voice_api.db.session import SessionFactory
from voice_api.models import Agent, AgentVersion
from voice_api.services.resolution_service import resolve


async def find_agent(session: AsyncSession, identifier: str) -> Agent | None:
    """Find agent by exact ID or case-insensitive name match."""
    # Try exact ID match
    agent = await session.get(Agent, identifier)
    if agent:
        return agent

    # Try exact name match
    agent = await session.scalar(select(Agent).where(Agent.name == identifier))
    if agent:
        return agent

    # Try partial name match
    agents = (
        await session.scalars(select(Agent).where(Agent.name.ilike(f"%{identifier}%")))
    ).all()
    if len(agents) == 1:
        return agents[0]
    if len(agents) > 1:
        names = ", ".join(f"'{a.name}' ({a.id})" for a in agents)
        raise ValueError(f"Ambiguous agent identifier '{identifier}'. Matches: {names}")
    return None


async def find_agent_version(
    session: AsyncSession, agent_id: str, version_selector: str
) -> AgentVersion:
    """Find specific version: integer, 'draft', 'published', or 'latest'."""
    query = (
        select(AgentVersion)
        .where(AgentVersion.agent_id == agent_id)
        .order_by(AgentVersion.version.desc())
    )
    versions = (await session.scalars(query)).all()
    if not versions:
        raise ValueError(f"No versions found for agent {agent_id}")

    sel = version_selector.strip().lower()
    if sel in ("latest", "head"):
        return versions[0]
    if sel == "draft":
        drafts = [v for v in versions if v.status == "draft"]
        if not drafts:
            raise ValueError(f"No draft version found for agent {agent_id}")
        return drafts[0]
    if sel == "published":
        published = [v for v in versions if v.status == "published"]
        if not published:
            raise ValueError(f"No published version found for agent {agent_id}")
        return published[0]

    # Try version number (e.g. "7" or "v7")
    clean_v = sel.lstrip("v")
    if clean_v.isdigit():
        target_num = int(clean_v)
        for v in versions:
            if v.version == target_num:
                return v
        available = ", ".join(f"v{v.version} ({v.status})" for v in versions)
        raise ValueError(
            f"Version {target_num} not found for agent {agent_id}. Available: {available}"
        )

    raise ValueError(
        f"Invalid version selector '{version_selector}'. Use a version number (e.g. 7), 'draft', 'published', or 'latest'."
    )


async def build_export(
    session: AsyncSession,
    agent: Agent,
    version: AgentVersion,
    export_format: str,
) -> dict[str, Any]:
    snapshot, fp = await resolve(session, version)

    if export_format == "resolved":
        return snapshot

    if export_format == "saved":
        return version.config or {}

    # Default: "full"
    return {
        "snapshot_type": "database_agent_version_export",
        "exported_at": datetime.now(UTC).isoformat(),
        "fingerprint": fp,
        "agent": {
            "id": agent.id,
            "name": agent.name,
            "archived_at": agent.archived_at.isoformat() if agent.archived_at else None,
        },
        "agent_version": {
            "id": version.id,
            "version": version.version,
            "revision": version.revision,
            "status": version.status,
            "note": version.note,
            "created_at": version.created_at.isoformat() if version.created_at else None,
            "published_at": version.published_at.isoformat() if version.published_at else None,
            "parent_id": version.parent_id,
        },
        "saved_config": version.config,
        "resolved_snapshot": snapshot,
    }


async def list_all_agents(session: AsyncSession) -> None:
    agents = (await session.scalars(select(Agent).order_by(Agent.name))).all()
    print("Available agents in database:")
    for a in agents:
        versions = (
            await session.scalars(
                select(AgentVersion)
                .where(AgentVersion.agent_id == a.id)
                .order_by(AgentVersion.version)
            )
        ).all()
        v_summary = ", ".join(f"v{v.version} ({v.status})" for v in versions)
        print(f"  • {a.name}")
        print(f"    ID: {a.id}")
        print(f"    Versions: {v_summary or 'none'}")


async def main_async(args: argparse.Namespace) -> tuple[str, str, int, str] | None:
    async with SessionFactory() as session:
        if args.list:
            await list_all_agents(session)
            return

        if not args.agent:
            print("Error: --agent is required (or use --list to view all agents)", file=sys.stderr)
            sys.exit(1)

        agent = await find_agent(session, args.agent)
        if not agent:
            print(f"Error: Agent '{args.agent}' not found.", file=sys.stderr)
            await list_all_agents(session)
            sys.exit(1)

        version = await find_agent_version(session, agent.id, args.version)
        export_data = await build_export(session, agent, version, args.format)

        indent = 2 if args.pretty else None
        output_json = json.dumps(export_data, indent=indent, ensure_ascii=False)
        return output_json, agent.name, version.version, version.status


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch any agent's draft or published version snapshot from the database."
    )
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        help="Agent ID, exact name, or partial name substring (e.g. 'Elevated Box', '19a11750...')",
    )
    parser.add_argument(
        "--version",
        "-v",
        type=str,
        default="latest",
        help="Version selector: version number (e.g. 7 or v7), 'draft', 'published', or 'latest' (default: latest)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["full", "resolved", "saved"],
        default="full",
        help="Export format: 'full' (agent metadata + saved config + resolved snapshot), 'resolved' (execution snapshot with _resolved bindings), or 'saved' (raw authoring config)",
    )
    parser.add_argument(
        "--out",
        "-o",
        type=str,
        help="Output file path. If omitted or '-', output is printed to stdout.",
    )
    parser.add_argument(
        "--compact",
        action="store_false",
        dest="pretty",
        default=True,
        help="Output compact single-line JSON instead of formatted JSON.",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all agents and their available versions in the database.",
    )

    args = parser.parse_args()
    res = asyncio.run(main_async(args))
    if not res:
        return

    output_json, agent_name, version_num, version_status = res
    if args.out and args.out != "-":
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json, encoding="utf-8")
        print(
            f"Successfully exported {agent_name} v{version_num} ({version_status}) to {out_path}",
            file=sys.stderr,
        )
    else:
        print(output_json)


if __name__ == "__main__":
    main()
