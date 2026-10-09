"""Use the existing single-save referral tool in the reviewed local v10 draft."""

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path

from sqlalchemy.engine import make_url
from voice_api.api.v1.endpoints.agents import validate_agent_bindings, validate_callback_calendars
from voice_api.core.config import get_settings
from voice_api.db.session import SessionFactory
from voice_api.db.tenant_scope import bind_organization
from voice_api.models import Agent, AgentVersion, ToolVersion
from voice_api.services.publication_service import sync_bindings
from voice_api.services.resolution_service import resolve
from voice_runtime.contracts import AgentConfig

REFERRAL = """If they suggest someone else to speak to, ask ONE combined question for that person's name, best contact detail (phone or email, or both), and any useful context they can share; reuse information already given. Do not turn this into several collection questions or require optional details. Read back any supplied phone/email once and wait for explicit confirmation before saving. If corrected, read back the corrected values and confirm. Then call #save_referral ONCE with first_name, last_name only if supplied, phone_number and/or email in their existing separate parameters, and known role, organization and context (including timing, timezone, reason or restrictions if stated). Set contact_details_confirmed=true only after confirmation. Name-only referrals are valid; omit unknown values. Do not guess surnames, country codes, email or consent. Do not use conversation-fact tools for referrals or copy referral names into caller facts. Say saved only after status=saved. Saving creates a pending referral for review, not a caller Contact, booking, transfer or outreach permission. Do not send WhatsApp or book caller-bound actions for the referred person."""
CONFIRMATION = """Before saving any caller-supplied phone number or email, read the exact details back and wait for the caller to confirm; never treat the initial dictation as confirmation. For a different WhatsApp destination, read that number back and ask whether to send the agreed message to that number; wait for explicit confirmation before using the tool's to parameter. A referral number is never automatically a WhatsApp destination. Keep phone/email out of name facts; no extra contact-detail fact writes are needed."""


def simplify(config, binding):
    result = deepcopy(config)
    removed = {
        slot["key"]
        for slot in result["fact_slots"]
        if slot["key"] == "recepient_name" or slot["key"].startswith("referred_contact_")
    }
    result["fact_slots"] = [slot for slot in result["fact_slots"] if slot["key"] not in removed]
    prompt = result["system_prompt"]
    prompt = prompt.replace(
        "if they give a different name than {{name}} then #record_recepient_name", ""
    )
    prompt = prompt.replace("; confirmed caller: {{recepient_name}}", "")
    prompt = prompt.replace(
        "If a different caller name is given, preserve #record_recepient_name and record confirmed parts with #record_caller_first_name and #record_caller_last_name.",
        "If the current caller corrects their name, record only the changed, supplied parts with #record_caller_first_name and/or #record_caller_last_name; do not ask for a surname or make a full-name write. Reuse these confirmed parts for addressing the caller: {{caller_first_name}} {{caller_last_name}}. No name writes for merely greeting a known caller.",
    )
    result["system_prompt"] = prompt.strip() + "\n\n" + CONFIRMATION
    for node in result["flow"]["nodes"]:
        node["role_message"] = node["role_message"].split(
            "\n\nIf the caller asks us to speak to someone else,", 1
        )[0]
        node["functions"] = [
            function
            for function in node["functions"]
            if function["name"] not in {"record_" + key for key in removed}
        ]
        if node["id"] != "closing":
            node["role_message"] += "\n\n" + REFERRAL
            if not any(function["name"] == "save_referral" for function in node["functions"]):
                node["functions"].append({"name": "save_referral", "transition_only": False})
    result["tool_bindings"]["save_referral"] = binding
    result["context"]["summarizer"]["prompt"] = result["context"]["summarizer"]["prompt"].replace(
        "Preserve caller first/last name separately from referred contact full name, phone/email, role, permission and restrictions.",
        "Preserve confirmed caller first/last names and referral details/results from save_referral separately, including phone/email readback confirmation, role/context and restrictions. Do not request redundant fact writes or infer confirmation.",
    )
    return result


async def main(backup, apply):
    url = make_url(get_settings().database_url)
    if (url.host, url.port, url.database) != ("localhost", 55432, "voice"):
        raise RuntimeError("Only authorized localhost:55432/voice may be updated")
    source = json.loads(await asyncio.to_thread(Path(backup).read_text, encoding="utf-8"))
    referral = [
        tool
        for tool in source["tools"]
        if tool["config"].get("handler") == "save_referral" and tool["status"] == "published"
    ]
    if len(referral) != 1:
        raise RuntimeError("Review referral tool versions before selecting a binding")
    async with SessionFactory() as session:
        bind_organization(session.sync_session, source["org_id"])
        version = await session.get(AgentVersion, source["id"], with_for_update=True)
        if (
            not version
            or version.status != "draft"
            or version.revision != source["revision"]
            or version.config != source["config"]
        ):
            raise RuntimeError("Draft changed since review")
        tool = await session.get(ToolVersion, referral[0]["id"])
        if tool.config != referral[0]["config"] or tool.status != "published":
            raise RuntimeError("Referral tool changed since review")
        agent = await session.get(Agent, version.agent_id)
        active = agent.active_version_id
        config = AgentConfig.model_validate(
            simplify(version.config, {"tool_id": tool.tool_id, "tool_version_id": tool.id})
        ).model_dump(mode="json", exclude_none=True)
        serialized = json.dumps(config)
        if "recepient_name" in serialized or "record_referred_contact_" in serialized:
            raise RuntimeError("Obsolete facts/references remain")
        for key in ("classifier", "callback_scheduling", "composer", "stt", "tts", "llm"):
            if config[key] != version.config[key]:
                raise RuntimeError(f"Unexpected {key} change")
        await validate_callback_calendars(session, AgentConfig.model_validate(config))
        version.config = config
        version.revision += 1
        await sync_bindings(session, version)
        await validate_agent_bindings(session, version)
        await resolve(session, version)
        if agent.active_version_id != active:
            raise RuntimeError("Active version changed")
        if apply:
            await session.commit()
            await session.refresh(version)
            assert version.config == config and version.revision == source["revision"] + 1
        else:
            await session.rollback()
        print(
            json.dumps(
                {
                    "applied": apply,
                    "revision": source["revision"] + 1,
                    "facts": [slot["key"] for slot in config["fact_slots"]],
                    "referral_tool": referral[0]["id"],
                    "active_version_unchanged": active,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.backup, args.apply))
