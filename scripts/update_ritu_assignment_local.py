"""Repair the local Ritu draft's pitch, catalog and mandatory follow-up paths.

No calls/messages/provider requests. Published versions and running snapshots stay immutable.
Run with --apply to save revision 37 in the local testing DB only.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from voice_api.api.v1.endpoints.agents import validate_agent_bindings, validate_callback_calendars
from voice_api.core.config import get_settings
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_run_organization
from voice_api.models import AgentVersion, ToolVersion
from voice_api.models.common import new_id
from voice_api.services.publication_service import sync_bindings
from voice_api.services.resolution_service import resolve
from voice_runtime.contracts import AgentConfig, ToolConfig

VERSION = "8a5274df-319b-41a0-b3f1-a068828f89fa"
RUN = "b1d927c2-c87b-4c26-b6e5-bc486b1a69c4"
WA = "whatsapp_template_dialtone_followup"
FOLLOWUP = """FOLLOW-UP RULES:
This assignment requires one contextual WhatsApp follow-up with the hosted prototype link, during the call for high intent or before the final farewell otherwise. No additional permission question is required. A catalog/details/WhatsApp request is actionable now, not a reason to substitute a callback. Never invent a catalog: send the existing service/reference link and relevant conversation context with #whatsapp_template_dialtone_followup. Use the actual caller name and only confirmed needs, budget, products, features, timeframe and booking outcomes; omit unknowns. Include Live App = https://omkars-voice-ai.netlify.app/ in Summary. The configured template already provides the build image; do not claim other attachments were sent.
whatsapp_sent: {{whatsapp_sent}}. A successful provider result automatically records this fact; #record_whatsapp_sent with value true may confirm it only after the tool returns a real message_id. Sent means accepted by WhatsApp, not delivered or read. Never resend when already confirmed, in progress, failed or uncertain. Do not say sent until confirmed. An explicit no-WhatsApp/opt-out overrides this follow-up. A busy/callback request preserves their timing and does not itself mean no WhatsApp. Do not ask an extra permission question or prolong a busy caller's conversation for a pitch. Never repeat a write to make a closing requirement appear successful."""
STAGES = {
    "discovery_and_qualify": """CURRENT PHASE: DISCOVERY AND QUALIFICATION
Understand their business and ecommerce requirement conversationally: products, current ordering/payment/shipping process, approximate catalog/order size, needed features, timeline and budget when useful. Reuse answered details; one focused question at a time, never a questionnaire.
After the first concrete need, make one short relevant pitch rather than only collecting answers. Explain how a web store can reduce the specific manual work they described; verify requested integrations/scoping rather than promising capability. Explain working style in one sentence: weekly milestones, Friday demos, sign-off before the next phase and payment for accepted milestones. Supported reference only when useful: MVP sprint USD 8k-15k and typically 3-4 weeks, subject to human scoping. For specifics, #query_service_reference with a narrow English keyword query; use only relevant excerpts.
A request for a catalog/details/WhatsApp: send the contextual reference now with #whatsapp_template_dialtone_followup, then return to the caller's next step. Do not replace this request with a sales-team call or claim a generic catalog exists.
Once a concrete need plus meaningful intent/readiness is clear, call #classify_lead once with no arguments; its configured table routes automatically. Comparing agencies does not negate buying intent. Do not continue repetitive discovery while enough context is available. Callback requests -> #go_to_callback_scheduling carrying all stated time and requirements; stop -> #go_to_closing. Never invent a classifier result.""",
    "hot_followup": """CURRENT PHASE: HOT FOLLOW-UP
Acknowledge their specific requirement and give one short benefit tied to it. If no pitch/working-style explanation has occurred, explain it briefly: weekly milestones, Friday demos and sign-off/payment for accepted milestones, subject to scoping. Do not repeat discovery.
Send #whatsapp_template_dialtone_followup now with their actual requirements and reference link if no attempt has occurred; do not gate it behind permission or a callback. Wait for the outcome and speak truthfully. Mention the 15% offer for qualified leads scheduling this week, subject to human confirmation; never invent an expiry or eligibility.
Then offer a 15-minute technical solutions scoping callback. A stated callback time -> #go_to_callback_scheduling immediately, preserving it. A callback request does not cancel the follow-up. No callback -> #go_to_closing. Explicit stop/opt-out ends sales actions.""",
    "callback_scheduling": """CURRENT PHASE: CALLBACK SCHEDULING
Arrange a 15-minute callback, never ask duration or restart qualification. Preserve any requested day/time/range, clarify only missing information. #check_callback_availability returns authoritative slots; offer exact display labels and call #book_callback with a selected returned slot_id and factual reason once accepted. An exact requested available time can count as acceptance. Confirm only the returned time/team after success. Definitive booking failure may use #schedule_callback to record an agreed request, not a confirmed appointment; no fallback or duplicate after uncertainty.
A catalog/details/WhatsApp request must be fulfilled here with #whatsapp_template_dialtone_followup, not deferred to the team. After handling their timing, if they have discussed a real requirement and have not heard the pitch, add one concise benefit and working-style sentence: weekly milestones, Friday demos, sign-off before the next phase and payment for accepted milestones. Skip the pitch if they explicitly cannot talk or opt out.
Before #go_to_closing, send the required contextual WhatsApp once if not attempted and not opted out; include only confirmed booking details. If already sent, do not resend. No extra permission question. Once outcomes are handled, go to closing without asking a generic 'anything else' question.""",
    "closing": """CURRENT PHASE: CLOSING
Before the farewell, if no WhatsApp has been attempted and there is no explicit messaging refusal/opt-out, call #whatsapp_template_dialtone_followup once with the factual conversation context and hosted reference link. Do not ask permission. Do not retry any prior failed/uncertain attempt or duplicate a confirmed send. #record_whatsapp_sent may confirm true only after an acknowledged provider message_id; never set it to manufacture success.
After the result, give one short natural farewell in their language. Mention only confirmed booking/message outcomes if useful. On failure/uncertainty, say the message could not be confirmed, never that the team will send it unless actually arranged. No new questions or sales pitch. End after the final output is delivered.""",
}


def repair(config):
    config = deepcopy(config)
    slots = config.setdefault("fact_slots", [])
    if not any(s["key"] == "whatsapp_sent" for s in slots):
        slots.append(
            {
                "key": "whatsapp_sent",
                "description": "WhatsApp follow-up accepted with a confirmed provider message ID; not proof of delivery. Runtime-derived, never guessed.",
                "value_type": "boolean",
                "nodes": [],
            }
        )
    for node in config["flow"]["nodes"]:
        original = node.get("role_message", "")
        marker = "CURRENT PHASE:"
        if node["id"] == "callback_scheduling":
            marker = "CURRENT_PHASE:"
        if node["id"] in STAGES:
            if node["id"] == "closing":
                header = original.split("Give one brief natural farewell", 1)[0]
            else:
                header = original.split(marker, 1)[0]
            node["role_message"] = header.rstrip() + "\n\n" + STAGES[node["id"]]
        node["role_message"] += "\n\n" + FOLLOWUP
        node["functions"] = [f for f in node.get("functions", []) if f.get("name") != WA] + [
            {"name": WA, "transition_only": False}
        ]
        if node["id"] in STAGES:
            node["task_messages"] = [
                {
                    "role": "user",
                    "content": {
                        "discovery_and_qualify": "Give one relevant pitch, understand the need, act on details requests and classify when ready.",
                        "hot_followup": "Send the contextual WhatsApp now, explain the benefit/offer and agree the next step.",
                        "callback_scheduling": "Preserve requested timing, book truthfully, fulfil details requests and send the required follow-up once.",
                        "closing": "Finish the one required follow-up if never attempted, then give a truthful farewell.",
                    }[node["id"]],
                }
            ]
        for f in node.get("functions", []):
            if f.get("name") == "classify_lead" and isinstance(f.get("transition_to"), dict):
                f["transition_to"]["default"] = None
                f["transition_to"]["cases"]["hot|possible_fit|receptive"] = "hot_followup"
    return config


async def main(apply=False):
    url = make_url(get_settings().database_url)
    if url.host not in {"localhost", "127.0.0.1"} or url.port != 55433 or url.database != "voice":
        raise RuntimeError("Local testing database 55433/voice required")
    async with SessionFactory() as session:
        await bind_run_organization(session, RUN)
        version = await session.get(AgentVersion, VERSION, with_for_update=True)
        if version.status != "draft" or version.revision != 36:
            raise RuntimeError(
                "Expected Ritu draft revision 36; review newer edits before applying"
            )
        config = repair(version.config)
        binding = config["tool_bindings"][WA]
        source = await session.get(ToolVersion, binding["tool_version_id"])
        tool_config = deepcopy(source.config)
        tool_config["description"] = (
            "Send the one required assignment follow-up with factual call context and the existing prototype link. No extra permission question. Respect explicit messaging opt-out. Never duplicate a confirmed, failed or uncertain attempt."
        )
        ToolConfig.model_validate(tool_config)
        number = await session.scalar(
            select(func.max(ToolVersion.version)).where(ToolVersion.tool_id == source.tool_id)
        )
        new_tool = ToolVersion(
            id=new_id(),
            tool_id=source.tool_id,
            org_id=source.org_id,
            version=number + 1,
            revision=1,
            status="published",
            published_at=datetime.now(UTC),
            parent_id=source.id,
            config=tool_config,
        )
        session.add(new_tool)
        binding["tool_version_id"] = new_tool.id
        parsed = AgentConfig.model_validate(config)
        await validate_callback_calendars(session, parsed)
        version.config = parsed.model_dump(mode="json", exclude_none=True)
        version.revision += 1
        await sync_bindings(session, version)
        await validate_agent_bindings(session, version)
        await resolve(session, version)
        print(
            "Validated local draft",
            version.id,
            "revision",
            version.revision,
            "WhatsApp fact and all-node tool availability",
        )
        if apply:
            await session.commit()
            print(
                "Saved locally. Existing running conversations retain their frozen revision; start a new conversation."
            )
        else:
            await session.rollback()
            print("Dry run only; rolled back.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
