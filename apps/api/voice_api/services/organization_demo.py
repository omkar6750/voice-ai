"""Credential-free starter and an allowlisted copy of one real completed call."""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from voice_runtime.contracts import AgentConfig, FlowConfig, FlowMessageConfig, FlowNodeConfig

from voice_api.models import (
    AgentVersion,
    ConversationMessage,
    Exchange,
    FlowNodeVisit,
    Run,
    TraceSpan,
)
from voice_api.models.common import new_id
from voice_api.services.resolution_service import fingerprint

FIXTURE_PATH = Path(__file__).with_name("organization_demo.json")


def demo_agent_config() -> AgentConfig:
    """A starting flow with no external actions, contacts or credentials."""
    return AgentConfig(
        name="Ritu — Project demo",
        system_prompt=(
            "You are Ritu, an AI assistant explaining this voice-agent platform. "
            "Continue the conversation naturally; ask one question at a time and wait "
            "for the answer. Match the caller's language. Keep replies brief and say "
            "numbers in words for speech. Do not restart introductions after transitions. "
            "This starter has no WhatsApp or calendar connection: never claim to send "
            "messages or book meetings. Explain that an operator can configure those tools. "
            "On goodbye or a request to stop, move immediately to the closing conversation step."
        ),
        flow=FlowConfig(
            initial_node="greeting",
            prompt_composition="global_plus_node",
            nodes=[
                FlowNodeConfig(
                    id="greeting",
                    task_messages=[
                        FlowMessageConfig(
                            role="user",
                            content="Introduce yourself briefly and ask if I would like a short project walkthrough.",
                        )
                    ],
                    prompt=(
                        "Introduce yourself as Ritu, the project's AI demo assistant. Ask if "
                        "the caller would like a short walkthrough. On agreement call "
                        "#go_to_project_pitch; do not deliver the pitch here. On goodbye call #go_to_closing."
                    ),
                    transitions=["project_pitch", "closing"],
                ),
                FlowNodeConfig(
                    id="project_pitch",
                    prompt=(
                        "Briefly explain that the platform creates voice agents, with a "
                        "dashboard for versioned prompts, flows and call diagnostics. The "
                        "FastAPI control plane stores configuration and evidence; Pipecat "
                        "handles live conversation. Browser calls work without telephony; "
                        "a local Waveshare modem supports cellular calling. Ask which part "
                        "interests the caller, then wait. Only on their next reply call "
                        "#go_to_project_qa, preserving their question. On goodbye call #go_to_closing."
                    ),
                    transitions=["project_qa", "closing"],
                ),
                FlowNodeConfig(
                    id="project_qa",
                    prompt=(
                        "Continue naturally and answer the caller's question without another "
                        "introduction or pitch. Explain published agent versions, traceable "
                        "tool calls, transcripts, provider timing and organization isolation "
                        "when relevant. Sarvam supplies speech services; operators select "
                        "models and their own keys. Be honest about unknown details and do "
                        "not invent results. When finished call #go_to_closing."
                    ),
                    transitions=["closing"],
                ),
                FlowNodeConfig(
                    id="closing",
                    terminal=True,
                    prompt="Give one short farewell in the caller's language. No questions or further actions.",
                    post_actions=[{"type": "end_conversation"}],
                ),
            ],
        ).model_dump(mode="json"),
        llm={
            "provider": "sarvam",
            "model": "sarvam-105b-conversations",
            "temperature": 0.5,
            "max_tokens": 256,
        },
        stt={"provider": "sarvam", "model": "saaras:v3-realtime"},
        tts={"provider": "sarvam", "model": "bulbul:v3", "voice": "ritu"},
        classifier={"enabled": False},
        composer={"enabled": False},
    )


def demo_fixture() -> dict:
    # Fixed packaged resource, never a tenant path or an environment URL.
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _dates(row: dict) -> dict:
    return {
        key: datetime.fromisoformat(value) if key.endswith("_at") and value else value
        for key, value in row.items()
    }


async def seed_demo_run(session: AsyncSession, org_id: str, version: AgentVersion) -> None:
    fixture = demo_fixture()
    run_id = new_id()
    provenance = {
        key: fixture[key]
        for key in ("manifest", "source_run_id", "source_agent", "source_agent_version", "notice")
    }
    snapshot = {
        **version.config,
        "_demo": provenance,
        "_resolved": {
            "schema_version": 1,
            "agent_version_id": version.id,
            "tools": {},
            "knowledge": [],
            "credentials": {},
        },
    }
    session.add(
        Run(
            id=run_id,
            org_id=org_id,
            **_dates(fixture["run"]),
            transport_provider="sim7600",
            agent_version_id=version.id,
            resolved_config=snapshot,
            config_hash=fingerprint(snapshot),
            snapshot_schema_version=1,
            contact_snapshot={"name": "Demo — Project walkthrough (redacted)"},
            final_state={"demo": provenance},
        )
    )
    await session.flush()
    exchange_ids = {row["id"]: new_id() for row in fixture["exchanges"]}
    for row in fixture["exchanges"]:
        session.add(
            Exchange(
                **_dates({key: value for key, value in row.items() if key != "id"}),
                id=exchange_ids[row["id"]],
                org_id=org_id,
                run_id=run_id,
            )
        )
    await session.flush()
    for row in fixture["messages"]:
        session.add(
            ConversationMessage(
                **_dates({key: value for key, value in row.items() if key != "exchange_id"}),
                id=new_id(),
                org_id=org_id,
                run_id=run_id,
                exchange_id=exchange_ids[row["exchange_id"]],
            )
        )
    span_ids = {row["id"]: new_id() for row in fixture["spans"]}
    spans = {}
    for row in fixture["spans"]:
        span = TraceSpan(
            **_dates(
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"id", "exchange_id", "parent_id"}
                }
            ),
            id=span_ids[row["id"]],
            org_id=org_id,
            run_id=run_id,
            exchange_id=exchange_ids.get(row["exchange_id"]),
            output_state="not_recorded",
            attributes={"demo": True},
        )
        session.add(span)
        spans[row["id"]] = span
    # Parents must exist before same-run foreign keys can reference them.
    await session.flush()
    for row in fixture["spans"]:
        spans[row["id"]].parent_id = span_ids.get(row["parent_id"])
    for row in fixture["visits"]:
        session.add(
            FlowNodeVisit(
                **_dates({key: value for key, value in row.items() if key != "span_id"}),
                id=new_id(),
                org_id=org_id,
                run_id=run_id,
                span_id=span_ids[row["span_id"]],
            )
        )
    await session.flush()
