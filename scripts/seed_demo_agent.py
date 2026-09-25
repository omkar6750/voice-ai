import asyncio
import os
from datetime import UTC, datetime

from sqlalchemy import select
from voice_api.core.config import get_settings
from voice_api.db.session import SessionFactory
from voice_api.models import (
    Agent,
    AgentVersion,
    Contact,
    IntegrationConnection,
    IntegrationSecret,
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
from voice_api.services.vault_service import CredentialVault
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
    ToolConfig,
    TTSConfig,
    VADConfig,
)

AGENT_SYSTEM_INSTRUCTION = (
    "You are Ava, a professional and friendly Senior Sales Development Representative at Northstar Software Studio. "
    "You are conducting an outbound phone follow-up to a lead who clicked our ad requesting custom software consultation. "
    "Speak naturally like a sharp, genuine professional on a live phone call. Never mention that you are an AI.\n"
    "--- SPOKEN CONVERSATION RULES ---\n"
    "1. Keep turns concise: 1 to 2 spoken sentences per turn. Complete your sentences naturally without trailing off.\n"
    "2. Ask only ONE focused question at a time.\n"
    "3. Keep discovery questions open; provide examples only when the caller asks for clarification.\n"
    "4. Acknowledge the caller's points with a brief, punchy summary rather than repeating everything they said.\n"
    "5. Plain speech only: never use asterisks, markdown formatting, bullet points, or numbered lists.\n"
    "6. If the caller asks about project risk or guarantees, reassure them that we work in weekly milestone sprints with regular demos and transparent sign-offs before each phase.\n"
    "--- MULTILINGUAL & CODE-MIXING RULES ---\n"
    "You are completely fluent in English, Hindi, and Marathi, and naturally code-mix like a modern Indian tech professional.\n"
    "1. Language Locking: When the caller speaks in or requests Marathi (e.g. 'मला मराठीत बोलायचे आहे') or Hindi, IMMEDIATELY switch to that language and STAY in that language consistently for the rest of the conversation.\n"
    "2. NEVER use English meta-excuses like 'मी इंग्रजीत चालवतो' or 'I will speak in English'. Reply directly in fluent, natural Marathi or Hindi in Devanagari script!\n"
    "3. Natural Marathi Examples:\n"
    "   - Greeting/Agreement: 'हो नक्कीच! आपण मराठीत बोलू शकतो. तुमच्या प्रोजेक्टबद्दल सांगा — वेब की मोबाईल अ‍ॅप बनवायचे आहे?'\n"
    "   - Pricing & Catalog: 'आमचा MVP Sprint पॅकेज $8k ते $15k मध्ये 3-4 आठवड्यांत तयार होतो. मी आपल्या WhatsApp वर आमचा संपूर्ण कॅटलॉग आणि प्राईसिंग पाठवून देतो.'\n"
    "   - Scheduling: 'नक्कीच! उद्या तुम्हाला कोणता वेळ सोयीचा पडेल — सकाळी की दुपारी?'\n"
    "--- FLOW & TOOL RULES ---\n"
    "Use change_node to guide the call forward through each stage:\n"
    "- In greeting, when they agree to talk -> change_node(node='discovery')\n"
    "- In discovery, once they share what they are building -> change_node(node='qualification')\n"
    "- In qualification, understand their platform and broad use case, then transition -> change_node(node='hot_pricing')\n"
    "- In hot_pricing, state our MVP sprint pricing, offer the catalog, and call send_whatsapp_template(caller_name=...)\n"
    "- If at any point the caller asks for a callback tomorrow or later -> change_node(node='callback_scheduling')\n"
    "- When concluding or finished -> immediately call end_call()."
)

NORTHSTAR_KNOWLEDGE_DOCUMENT = """# Northstar Software Studio - Knowledge Base & Service Guide

## About Us
Northstar Software Studio is an elite software engineering agency specializing in high-performance web applications, mobile apps (iOS and Android with Flutter / React Native), and AI-native cloud backend architectures.

## Core Offerings & MVP Sprint Pricing
- **MVP Sprint Package**: $8,000 to $15,000.
  - Delivery Timeline: 3 to 4 weeks for a fully functional, production-ready MVP.
  - Quarterly Incentive: 15% discount applied for qualified leads who schedule a scoping session this week.
- **Dedicated Tech Team / Scale-up**: Custom dedicated engineering teams starting at $12,000/month per full-stack engineer.

## Architecture & Tech Stacks
- **Frontend**: Next.js, React, Vite, TypeScript, Tailwind CSS, pixel-perfect motion graphics.
- **Mobile**: Native Flutter, React Native, iOS Swift, Android Kotlin.
- **Backend**: FastAPI (Python), Node.js / NestJS, Go, PostgreSQL with pgvector, Redis, Apache Kafka.
- **AI & Automation**: Voice AI Pipelines (Pipecat, Sarvam, Groq, Whisper, Cartesia), LLM Agent Orchestration, RAG vector search.
- **Cloud Infrastructure**: AWS, Google Cloud, Docker, Kubernetes, automated CI/CD pipelines.

## Risk Guarantees & Milestones
- We work in weekly milestone sprints.
- Regular live demos every Friday.
- Transparent sign-offs before moving to the next phase; clients only pay for accepted milestones.
"""


async def seed() -> None:
    print("Seeding Northstar SDR Agent, Tools, and Integrations into PostgreSQL...")
    settings = get_settings()

    async with SessionFactory() as session:
        # 1. Initialize WorkspaceSettings
        ws = await session.get(WorkspaceSettings, 1)
        if ws is None:
            ws = WorkspaceSettings(id=1, revision=1, config={})
            session.add(ws)
            await session.commit()
            print("  [+] WorkspaceSettings initialized.")

        # 2. Create Tools
        tools_definitions = [
            (
                "change_node",
                "Transition conversation to a new dialogue stage.",
                {
                    "type": "object",
                    "properties": {
                        "node": {
                            "type": "string",
                            "enum": [
                                "greeting",
                                "discovery",
                                "qualification",
                                "hot_pricing",
                                "warm_nurture",
                                "closing",
                                "callback_scheduling",
                                "diplomatic_exit",
                            ],
                        }
                    },
                    "required": ["node"],
                },
            ),
            (
                "end_call",
                "Gracefully terminate the phone call.",
                {"type": "object", "properties": {}},
            ),
            (
                "send_whatsapp_template",
                "Dispatch the pre-approved WhatsApp catalog and follow-up template.",
                {
                    "type": "object",
                    "properties": {
                        "caller_name": {
                            "type": "string",
                            "description": "The name of the caller.",
                        }
                    },
                },
            ),
            (
                "send_followup",
                "Send a direct custom WhatsApp follow-up message.",
                {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Custom message text"}
                    },
                },
            ),
            (
                "schedule_callback",
                "Schedule a callback for a requested date and time mentioned by the caller.",
                {
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "string",
                            "description": "The date and time requested by the caller (e.g., 'tomorrow morning', 'Monday at 2 PM').",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Optional reason or topic for the callback.",
                        },
                    },
                    "required": ["time"],
                },
            ),
        ]

        published_tool_versions: dict[str, tuple[str, str]] = {}
        for name, desc, params in tools_definitions:
            tool = await session.scalar(select(Tool).where(Tool.name == name))
            if tool is None:
                tool = Tool(id=new_id(), name=name)
                session.add(tool)
                await session.flush()

            version = await session.scalar(
                select(ToolVersion).where(
                    ToolVersion.tool_id == tool.id, ToolVersion.status == "published"
                )
            )
            if version is None:
                version = await session.scalar(
                    select(ToolVersion).where(
                        ToolVersion.tool_id == tool.id, ToolVersion.status == "draft"
                    )
                )
                config = ToolConfig(
                    name=name,
                    description=desc,
                    kind="registered",
                    handler=name,
                    parameters=params,
                ).model_dump(mode="json")
                if version is None:
                    version = ToolVersion(
                        id=new_id(),
                        tool_id=tool.id,
                        version=1,
                        revision=1,
                        status="published",
                        published_at=datetime.now(UTC),
                        config=config,
                    )
                    session.add(version)
                else:
                    version.config = config
                    version.status = "published"
                    version.published_at = datetime.now(UTC)
                await session.flush()
            published_tool_versions[name] = (tool.id, version.id)
            print(f"  [+] Tool published: {name} (Version ID: {version.id})")

        # 3. Create WhatsApp Integration Connection & Encrypted Secret
        wa_conn = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.label == "Northstar WhatsApp Official"
            )
        )
        if wa_conn is None:
            wa_conn = IntegrationConnection(
                id=new_id(),
                label="Northstar WhatsApp Official",
                provider="whatsapp",
                enabled=True,
                config={
                    "phone_number_id": os.getenv(
                        "VOICE_WHATSAPP_PHONE_NUMBER_ID", "1355945384265199"
                    ),
                    "waba_id": os.getenv("VOICE_WHATSAPP_PHONE_NUMBER_ID", "1355945384265199"),
                    "api_version": "v23.0",
                },
            )
            session.add(wa_conn)
            await session.flush()

        token = os.getenv("VOICE_WHATSAPP_ACCESS_TOKEN", "")
        if token:
            vault = CredentialVault.from_env()
            enc = vault.encrypt(token)
            secret = await session.scalar(
                select(IntegrationSecret).where(
                    IntegrationSecret.connection_id == wa_conn.id,
                    IntegrationSecret.name == "access_token",
                )
            )
            if secret is None:
                secret = IntegrationSecret(
                    id=new_id(),
                    connection_id=wa_conn.id,
                    name="access_token",
                    ciphertext=enc.ciphertext,
                    key_id=enc.key_id,
                )
                session.add(secret)
            else:
                secret.ciphertext, secret.key_id = enc.ciphertext, enc.key_id
            await session.flush()
            print(
                f"  [+] WhatsApp access_token encrypted & saved in vault (Connection ID: {wa_conn.id})"
            )

        # 4. Create Knowledge Base & Ingest Source
        kb = await session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.name == "Northstar Software Studio Knowledge Base"
            )
        )
        if kb is None:
            kb = KnowledgeConfig(
                chunk_size=500,
                chunk_overlap=50,
                markdown_aware=True,
                supported_sources=["text", "markdown", "pdf", "txt"],
            )
            kb_row = KnowledgeBase(
                id=new_id(),
                name="Northstar Software Studio Knowledge Base",
                config=kb.model_dump(mode="json"),
            )
            session.add(kb_row)
            await session.flush()
            kb_id = kb_row.id
        else:
            kb_id = kb.id

        source = await session.scalar(
            select(KnowledgeSource).where(
                KnowledgeSource.knowledge_base_id == kb_id,
                KnowledgeSource.title == "Northstar Service & Pricing Guide",
            )
        )
        if source is None:
            source = KnowledgeSource(
                id=new_id(),
                knowledge_base_id=kb_id,
                title="Northstar Service & Pricing Guide",
                content=NORTHSTAR_KNOWLEDGE_DOCUMENT,
                kind="md",
                status="ready",
                ingestion_token=new_id(),
            )
            session.add(source)
            await session.flush()

            # Generate chunks
            chunks = chunk_markdown(NORTHSTAR_KNOWLEDGE_DOCUMENT, 500, 50, markdown_aware=True)
            for ordinal, chunk in enumerate(chunks):
                session.add(
                    KnowledgeChunk(
                        id=new_id(),
                        source_id=source.id,
                        ordinal=ordinal,
                        content=chunk.content,
                        embedding=[0.0] * 768,  # Default vector structure
                        embedding_model="gemini-embedding-001",
                        ingestion_token=source.ingestion_token,
                        metadata_json=chunk.metadata,
                    )
                )
            await session.flush()
            print(f"  [+] Knowledge Base seeded: {kb_id} (Source Chunks: {len(chunks)})")

        # 5. Create Agent with 8-Node FlowConfig
        flow_nodes = [
            FlowNodeConfig(
                id="greeting",
                prompt=(
                    "You are Ava from Northstar Software Studio. Warmly greet the caller, introduce yourself, "
                    "and mention you are following up on their interest in custom software development. "
                    "Ask if they have two quick minutes to chat right now. "
                    "When they agree, call change_node(node='discovery'). "
                    "If busy, call change_node(node='callback_scheduling'). "
                    "If not interested, call change_node(node='diplomatic_exit')."
                ),
                transitions=["discovery", "callback_scheduling", "diplomatic_exit"],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="discovery",
                prompt=(
                    "You are in discovery. Ask for their name if not known, and ask what kind of project they are looking to build. "
                    "Keep your question open. Once they share their idea, acknowledge warmly and call change_node(node='qualification'). "
                    "If they ask to be called back later, call change_node(node='callback_scheduling')."
                ),
                transitions=["qualification", "callback_scheduling", "diplomatic_exit"],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="qualification",
                prompt=(
                    "You are in qualification. Ask about platform (web/mobile) and their core use case. "
                    "Once you have a clear picture (or if they ask for pricing/timeline), call change_node(node='hot_pricing'). "
                    "If they ask for a callback, call change_node(node='callback_scheduling')."
                ),
                transitions=[
                    "hot_pricing",
                    "warm_nurture",
                    "callback_scheduling",
                    "diplomatic_exit",
                ],
                tool_bindings=["change_node", "end_call"],
            ),
            FlowNodeConfig(
                id="hot_pricing",
                prompt=(
                    "You are in pricing. State our MVP Sprint package ranges from $8k to $15k ready in 3-4 weeks with a 15% discount this quarter. "
                    "Offer to send our full portfolio and pricing catalog to their WhatsApp and CALL send_whatsapp_template(caller_name=...). "
                    "Ask if a quick 15-minute scoping call works for them. If agreed, call change_node(node='closing'). "
                    "If they want to pick a callback time, call change_node(node='callback_scheduling')."
                ),
                transitions=["closing", "callback_scheduling", "warm_nurture", "diplomatic_exit"],
                tool_bindings=[
                    "change_node",
                    "end_call",
                    "send_whatsapp_template",
                    "send_followup",
                ],
            ),
            FlowNodeConfig(
                id="warm_nurture",
                prompt=(
                    "You are in nurture. Reassure them that we build custom software tailored to their pace. "
                    "Offer to send our portfolio to their WhatsApp (call send_whatsapp_template). "
                    "If they agree to next steps, call change_node(node='closing') or change_node(node='callback_scheduling')."
                ),
                transitions=["closing", "callback_scheduling", "diplomatic_exit"],
                tool_bindings=["change_node", "end_call", "send_whatsapp_template"],
            ),
            FlowNodeConfig(
                id="callback_scheduling",
                prompt="Ask what day and time works best for a quick callback. Once provided, call schedule_callback(time=...) to record the callback. Then confirm warmly, assure them the WhatsApp catalog is on the way, and call end_call().",
                terminal=True,
                tool_bindings=[
                    "change_node",
                    "end_call",
                    "schedule_callback",
                    "send_whatsapp_template",
                ],
            ),
            FlowNodeConfig(
                id="diplomatic_exit",
                prompt="Thank them warmly for their time, offer to send our catalog to WhatsApp, and call end_call().",
                terminal=True,
                tool_bindings=["change_node", "end_call", "send_whatsapp_template"],
            ),
            FlowNodeConfig(
                id="closing",
                prompt="Let them know the WhatsApp message is on its way. Thank them warmly, say goodbye, and call end_call().",
                terminal=True,
                tool_bindings=["change_node", "end_call"],
            ),
        ]

        flow = FlowConfig(initial_node="greeting", nodes=flow_nodes)
        tool_bindings_dict = {
            name: ToolBinding(tool_id=t_id, tool_version_id=v_id)
            for name, (t_id, v_id) in published_tool_versions.items()
        }

        agent_config = AgentConfig(
            name="Ava @ Northstar Software Studio",
            persona="Senior Sales Development Representative",
            system_prompt=AGENT_SYSTEM_INSTRUCTION,
            language=LanguageConfig(
                default_language="en-IN", supported_languages=["en-IN", "hi-IN", "mr-IN", "te-IN"]
            ),
            flow=flow,
            tool_bindings=tool_bindings_dict,
            knowledge_base_ids=[kb_id],
            stt=STTConfig(provider="sarvam", model="saaras:v3"),
            llm=LLMConfig(
                provider="groq", model="qwen/qwen3.8-27b", max_tokens=180, temperature=0.4
            ),
            tts=TTSConfig(provider="sarvam", model="bulbul:v3", voice="ritu", language="en-IN"),
            vad=VADConfig(stop_secs=0.8, start_secs=0.1, confidence=0.5),
            call_limits=CallLimits(max_duration_secs=600, idle_timeout_secs=60),
        )

        agent = await session.scalar(
            select(Agent).where(Agent.name == "Ava @ Northstar Software Studio")
        )
        if agent is None:
            agent = Agent(id=new_id(), name="Ava @ Northstar Software Studio")
            session.add(agent)
            await session.flush()

        agent_ver = await session.scalar(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent.id, AgentVersion.status == "published")
            .order_by(AgentVersion.version.desc())
        )
        if (
            agent_ver is None
            or agent_ver.config.get("call_limits", {}).get("max_duration_secs") != 600
        ):
            next_version = 1 if agent_ver is None else agent_ver.version + 1
            new_ver = AgentVersion(
                id=new_id(),
                agent_id=agent.id,
                version=next_version,
                revision=1,
                status="draft",
                config=agent_config.model_dump(mode="json"),
            )
            session.add(new_ver)
            await session.flush()
            await sync_bindings(session, new_ver)
            new_ver.status = "published"
            new_ver.published_at = datetime.now(UTC)
            await session.flush()
            agent.active_version_id = new_ver.id
            await session.flush()
            agent_ver = new_ver
        else:
            agent.active_version_id = agent_ver.id
            await session.flush()

        print(
            f"  [+] Agent Published & Activated: {agent.id} (Version {agent_ver.version} ID: {agent_ver.id})"
        )

        # 6. Create RuntimeEndpoint for SIM7600 Hardware
        endpoint = await session.scalar(
            select(RuntimeEndpoint).where(RuntimeEndpoint.name == "SIM7600 USB Modem")
        )
        if endpoint is None:
            endpoint = RuntimeEndpoint(
                id=new_id(),
                name="SIM7600 USB Modem",
                config={
                    "provider": "sim7600",
                    "at_port": os.getenv("VOICE_MODEM_AT_PORT", "COM16"),
                    "audio_port": os.getenv("VOICE_MODEM_AUDIO_PORT", "COM17"),
                    "baudrate": int(os.getenv("VOICE_MODEM_BAUDRATE", "115200")),
                    "at_timeout_secs": 5.0,
                    "sample_rates": [16000],
                },
            )
            session.add(endpoint)
            await session.flush()
            print(f"  [+] Runtime Endpoint configured: {endpoint.id} (COM16/COM17)")

        # 7. Create/Update Contact
        contact = await session.scalar(
            select(Contact).where(Contact.phone_number == "+917304058886")
        )
        if contact is None:
            contact = Contact(
                id=new_id(),
                name="Omkar",
                phone_number="+917304058886",
                business="AI & Voice Systems",
                source="Inbound Web",
                language="en-IN",
                timezone="Asia/Kolkata",
            )
            session.add(contact)
            await session.flush()
            print(
                f"  [+] Contact created: {contact.name} ({contact.phone_number}) ID: {contact.id}"
            )

        await session.commit()

        print("\n" + "=" * 80)
        print("SEED COMPLETE: DATABASE CONFIGURED SUCCESSFULLY")
        print("=" * 80)
        print(f"Agent ID:           {agent.id}")
        print(f"Agent Version ID:   {agent_ver.id}")
        print(f"Contact ID:         {contact.id}")
        print(f"Endpoint ID:        {endpoint.id}")
        print(f"Operator Token:     {settings.operator_token}")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(seed())
