from pydantic import BaseModel, Field


class ToolConfig(BaseModel):
    name: str
    description: str


class FlowNode(BaseModel):
    id: str
    prompt: str
    next_node: str | None = None


class AgentConfig(BaseModel):
    name: str
    system_prompt: str
    greeting: str
    tools: list[ToolConfig] = Field(default_factory=list)
    flow_nodes: list[FlowNode] = Field(default_factory=list)


def default_agent_config() -> AgentConfig:
    return AgentConfig(
        name="sales-qualifier",
        system_prompt=(
            "You are a concise, polite sales qualification assistant. "
            "Ask one question at a time. Never invent lead details."
        ),
        greeting="Hello, this is the sales team. Is now a good time for a quick question?",
        tools=[
            ToolConfig(name="classify_lead", description="Classify lead intent and qualification."),
            ToolConfig(name="send_whatsapp", description="Send an approved WhatsApp follow-up."),
            ToolConfig(name="schedule_callback", description="Schedule a callback request."),
        ],
        flow_nodes=[
            FlowNode(
                id="introduction",
                prompt="Introduce yourself and ask for permission to continue.",
                next_node="discovery",
            ),
            FlowNode(
                id="discovery", prompt="Learn the lead's current need.", next_node="qualification"
            ),
            FlowNode(id="qualification", prompt="Ask whether the lead wants a follow-up."),
        ],
    )
