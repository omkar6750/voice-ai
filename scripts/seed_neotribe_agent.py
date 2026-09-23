"""Seed script for Deepankar Paria (Neotribe) and Maya (Omkar's Assistant Agent)."""

import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import select
from voice_api.db.session import SessionFactory
from voice_api.models import (
    Agent,
    AgentVersion,
    Contact,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeSource,
    RuntimeEndpoint,
    Tool,
    ToolVersion,
    WorkspaceSettings,
)
from voice_api.models.common import new_id
from voice_api.services.knowledge_service import chunk_markdown
from voice_api.services.publication_service import sync_bindings
from voice_runtime.contracts import (
    AgentConfig,
    CallLimits,
    FlowConfig,
    FlowNodeConfig,
    KnowledgeConfig,
    LanguageConfig,
    LLMConfig,
    STTConfig,
    ToolBinding,
    TTSConfig,
    VADConfig,
)

NEOTRIBE_AGENT_SYSTEM_INSTRUCTION = (
    "You are Maya, a sharp, friendly, and professional design & project assistant calling on behalf of Omkar. "
    "You are speaking directly with Deepankar Paria, the founder of Neotribe (a custom jewellery & apparel brand). "
    "Omkar has already developed the entire backend and core architecture of the Neotribe website; only the frontend UI is remaining to match their new brand aesthetic.\n"
    "\n--- CONVERSATION OBJECTIVES ---\n"
    "1. Deepankar is a friend and valued client. Speak warmly, naturally, and professionally like a real human assistant on a live phone call.\n"
    "2. Discuss the transition from the old aesthetic (cyber-sigilism, knights, witches) to the new Modern Indian Desi Maximalism / Indian Tribal jewellery theme.\n"
    "3. Check on the Diwali launch timeline, product packaging progress, and when they can share the new brand assets.\n"
    "4. Highlight that Omkar and the team can finish the complete UI in just 2-3 days once brand assets are provided.\n"
    "5. Offer and dispatch design catalogs / project summary over WhatsApp during the call.\n"
    "\n--- CRITICAL SPOKEN CONVERSATION RULES ---\n"
    "1. NEVER ENUMERATE QUESTIONS: Never say 'Question 1', 'Question 2', 'Firstly', 'Secondly', etc. Talk naturally.\n"
    "2. ASK ONLY ONE QUESTION AT A TIME: Never stack multiple questions into one turn.\n"
    "3. CONCISE TURNS: Keep responses to 1-2 punchy spoken sentences per turn. Never monologue.\n"
    "4. NATURAL CODE-MIXING: You are completely fluent in Indian English and Hinglish. Use natural phrasing.\n"
    "5. CLEAN TERMINATION: When concluding, say a warm, polite goodbye and immediately invoke end_call()."
)

NEOTRIBE_KNOWLEDGE_DOCUMENT = """# Neotribe Project Brief & Technical Status

## Client & Brand Overview
- **Brand Name**: Neotribe
- **Founder**: Deepankar
- **Product Category**: Contemporary Jewellery and Tribal Accessories.
- **Brand Evolution**: Transitioning from Cyber-sigilism / Gothic Mythical to **Modern Indian Desi Maximalism & Indian Tribal Theme**.
- **Inventory**: New jewellery stock has already been acquired.

## Development Status by Omkar
- **Backend & Database**: 100% built and deployed (Product catalog, cart, checkout, inventory management, user auth).
- **Remaining Scope**: Frontend UI redesign to match the new Indian Maximalism aesthetic.
- **Turnaround Time**: 2 to 3 days to deliver the full responsive UI once design assets are supplied.
- **Target Milestone**: Diwali Launch Campaign.
"""


async def seed_neotribe() -> None:
    print("Seeding Neotribe Campaign Agent & Contact into PostgreSQL...")

    async with SessionFactory() as session:
        # 1. Initialize WorkspaceSettings
        ws = await session.get(WorkspaceSettings, 1)
        if ws is None:
            ws = WorkspaceSettings(id=1, revision=1, config={})
            session.add(ws)
            await session.flush()

        # 2. Lookup existing published tools
        tool_names = ["change_node", "end_call", "send_whatsapp_template", "send_followup"]
        published_tool_versions: dict[str, tuple[str, str]] = {}

        for name in tool_names:
            tool = await session.scalar(select(Tool).where(Tool.name == name))
            if tool is None:
                raise RuntimeError(f"Tool {name} must exist; run seed_demo_agent.py first.")
            ver = await session.scalar(
                select(ToolVersion).where(
                    ToolVersion.tool_id == tool.id, ToolVersion.status == "published"
                )
            )
            if ver is None:
                raise RuntimeError(f"Published version for tool {name} not found.")
            published_tool_versions[name] = (tool.id, ver.id)

        # 3. Create Knowledge Base for Neotribe
        kb = await session.scalar(
            select(KnowledgeBase).where(KnowledgeBase.name == "Neotribe Project Knowledge Base")
        )
        if kb is None:
            kb_config = KnowledgeConfig(
                chunk_size=500,
                chunk_overlap=50,
                markdown_aware=True,
                supported_sources=["text", "markdown", "pdf", "txt"],
            )
            kb_row = KnowledgeBase(
                id=new_id(),
                name="Neotribe Project Knowledge Base",
                config=kb_config.model_dump(mode="json"),
            )
            session.add(kb_row)
            await session.flush()
            kb_id = kb_row.id
        else:
            kb_id = kb.id

        source = await session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.knowledge_base_id == kb_id,
                KnowledgeSource.title == "Neotribe Project Brief",
            )
        )
        if source is None:
            source = KnowledgeSource(
                id=new_id(),
                knowledge_base_id=kb_id,
                title="Neotribe Project Brief",
                content=NEOTRIBE_KNOWLEDGE_DOCUMENT,
                kind="md",
                status="ready",
                ingestion_token=new_id(),
            )
            session.add(source)
            await session.flush()

            chunks = chunk_markdown(NEOTRIBE_KNOWLEDGE_DOCUMENT, 500, 50, markdown_aware=True)
            for ordinal, chunk in enumerate(chunks):
                session.add(
                    KnowledgeChunk(
                        id=new_id(),
                        source_id=source.id,
                        ordinal=ordinal,
                        content=chunk.content,
                        embedding=[0.0] * 768,
                        embedding_model="gemini-embedding-001",
                        ingestion_token=source.ingestion_token,
                        metadata_json=chunk.metadata,
                    )
                )
            await session.flush()

        # 4. Create Tailored Dialogue State Machine
        flow_nodes = [
            FlowNodeConfig(
                id="greeting",
                prompt=(
                    "Warmly greet Deepankar by name: 'Good evening Deepankar! I am Maya, calling on behalf of Omkar regarding your Neotribe website. "
                    "Do you have two quick minutes to chat?' "
                    "When he agrees to talk, call change_node(node='brand_recap'). "
                    "If he is busy right now, call change_node(node='callback_scheduling'). "
                    "If he cannot talk at all, call change_node(node='polite_exit')."
                ),
                transitions=["brand_recap", "callback_scheduling", "polite_exit"],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="brand_recap",
                prompt=(
                    "Mention that Omkar has already built the full backend and core website structure, and you understand they are moving from the cyber-sigilism and knights aesthetic to the new Modern Indian Desi Maximalism theme for their jewellery stock. "
                    "Ask only this one question: 'When are you looking to start rolling out the new frontend designs?' "
                    "Once he responds, warmly acknowledge and call change_node(node='timeline_and_assets')."
                ),
                transitions=["timeline_and_assets", "callback_scheduling"],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="timeline_and_assets",
                prompt=(
                    "Acknowledge his reply. Mention that Omkar can finish the complete frontend UI in just 2 to 3 days once they share the design assets. "
                    "Ask: 'Are we still aiming for the Diwali launch deadline, and how is the packaging coming along?' "
                    "Once he answers, acknowledge and call change_node(node='whatsapp_catalog')."
                ),
                transitions=["whatsapp_catalog", "closing", "callback_scheduling"],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="whatsapp_catalog",
                prompt=(
                    "Offer to send our design references and the website catalog directly to his WhatsApp right now. "
                    "Call send_whatsapp_template(caller_name='Deepankar') or send_followup. "
                    "Ask if a quick sync with Omkar later this week works best to finalize things. "
                    "Once he answers, call change_node(node='closing')."
                ),
                transitions=["closing", "callback_scheduling"],
                tool_bindings=[
                    "change_node",
                    "end_call",
                    "send_whatsapp_template",
                    "send_followup",
                ],
            ),
            FlowNodeConfig(
                id="callback_scheduling",
                prompt=(
                    "Ask what day or time works best for Omkar to give him a quick ring. "
                    "Once provided, confirm warmly, say goodbye, and call end_call()."
                ),
                terminal=True,
                transitions=[],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="closing",
                prompt=(
                    "Let him know the WhatsApp message is on its way. Thank Deepankar warmly, let him know Omkar will follow up, say a polite goodbye, and call end_call()."
                ),
                terminal=True,
                transitions=[],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="polite_exit",
                prompt=(
                    "Politely thank Deepankar for his time, offer to follow up later on WhatsApp, say goodbye, and call end_call()."
                ),
                terminal=True,
                transitions=[],
                tool_bindings=["change_node", "end_call"],
            ),
        ]

        flow = FlowConfig(
            nodes=flow_nodes,
            initial_node="greeting",
            prompt_composition="node_only",
        )

        tool_bindings_dict = {
            name: ToolBinding(tool_id=t_id, tool_version_id=v_id)
            for name, (t_id, v_id) in published_tool_versions.items()
        }

        agent_config = AgentConfig(
            name="Maya (Omkar's Assistant @ Neotribe Project)",
            persona="Design & Technical Project Assistant to Omkar",
            system_prompt=NEOTRIBE_AGENT_SYSTEM_INSTRUCTION,
            language=LanguageConfig(
                default_language="en-IN",
                supported_languages=["en-IN", "hi-IN", "mr-IN"],
            ),
            flow=flow,
            tool_bindings=tool_bindings_dict,
            knowledge_base_ids=[kb_id],
            stt=STTConfig(provider="sarvam", model="saaras:v3"),
            llm=LLMConfig(
                provider="groq",
                model="qwen/qwen3.8-27b",
                max_tokens=180,
                temperature=0.35,
            ),
            tts=TTSConfig(provider="sarvam", model="bulbul:v3", voice="ritu", language="en-IN"),
            vad=VADConfig(stop_secs=0.8, start_secs=0.1, confidence=0.5),
            call_limits=CallLimits(max_duration_secs=600, idle_timeout_secs=60),
        )

        # 5. Create or Update Agent
        agent = await session.scalar(
            select(Agent).where(Agent.name == "Maya (Omkar's Assistant @ Neotribe Project)")
        )
        if agent is None:
            agent = Agent(id=new_id(), name="Maya (Omkar's Assistant @ Neotribe Project)")
            session.add(agent)
            await session.flush()

        agent_ver = await session.scalar(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id, AgentVersion.status == "published")
            .order_by(AgentVersion.version.desc())
        )
        if agent_ver is None:
            agent_ver = AgentVersion(
                id=new_id(),
                agent_id=agent.id,
                version=1,
                revision=1,
                status="draft",
                config=agent_config.model_dump(mode="json"),
            )
            session.add(agent_ver)
            await session.flush()
            await sync_bindings(session, agent_ver)
            agent_ver.status = "published"
            agent_ver.published_at = datetime.now(UTC)
            await session.flush()
            agent.active_version_id = agent_ver.id
            await session.flush()
        else:
            agent.active_version_id = agent_ver.id
            await session.flush()

        print(f"  [+] Agent Published & Activated: {agent.id} (Version ID: {agent_ver.id})")

        # 6. Lookup RuntimeEndpoint (SIM7600)
        endpoint = await session.scalar(
            select(RuntimeEndpoint).where(RuntimeEndpoint.name == "SIM7600 USB Modem")
        )
        if endpoint is None:
            endpoint = RuntimeEndpoint(
                id=new_id(),
                name="SIM7600 USB Modem",
                config={
                    "provider": "sim7600",
                    "at_port": "COM16",
                    "audio_port": "COM17",
                    "baudrate": 115200,
                    "at_timeout_secs": 5.0,
                    "sample_rates": [16000],
                },
            )
            session.add(endpoint)
            await session.flush()

        # 7. Create/Update Deepankar Paria Contact
        target_phone = os.environ.get("NEOTRIBE_CONTACT_PHONE", "+919876543210")
        contact = await session.scalar(select(Contact).where(Contact.phone_number == target_phone))
        if contact is None:
            contact = Contact(
                id=new_id(),
                name="Deepankar Paria",
                phone_number=target_phone,
                business="Neotribe (Jewellery & Apparel)",
                source="Personal Client",
                language="en-IN",
                timezone="Asia/Kolkata",
            )
            session.add(contact)
            await session.flush()
            print(f"  [+] Contact created: {contact.name} ID: {contact.id}")
        else:
            print(f"  [+] Contact exists: {contact.name} ID: {contact.id}")

        await session.commit()

        print("\n" + "=" * 80)
        print("NEOTRIBE AGENT SEEDED SUCCESSFULLY")
        print("=" * 80)
        print(f"Agent ID:           {agent.id}")
        print(f"Agent Version ID:   {agent_ver.id}")
        print(f"Contact ID:         {contact.id}")
        print(f"Endpoint ID:        {endpoint.id}")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(seed_neotribe())
