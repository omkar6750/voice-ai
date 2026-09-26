"""Agent-owned graphs, prompts, exact tool bindings, and runtime settings."""

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from .base import ConfigModel, Identifier
from .cadence import ClassifierConfig, SummarizerConfig
from .knowledge import RetrievalConfig
from .providers import AudioConfig, CallLimits, LLMConfig, STTConfig, TTSConfig, VADConfig
from .tools import ToolBinding


class FlowNodeConfig(ConfigModel):
    id: Identifier
    prompt: str = ""
    role_prompt: str | None = None
    context_strategy: Literal["append", "reset"] = "append"
    transitions: list[Identifier] = Field(default_factory=list)
    tool_bindings: list[Identifier] = Field(default_factory=list)
    entry_actions: list[Identifier] = Field(default_factory=list)
    exit_actions: list[Identifier] = Field(default_factory=list)
    respond_immediately: bool = True
    terminal: bool = False


class FlowConfig(ConfigModel):
    initial_node: Identifier
    nodes: list[FlowNodeConfig] = Field(min_length=1)
    prompt_composition: Literal["node_only", "global_plus_node"] = "node_only"

    @model_validator(mode="after")
    def valid_graph(self):
        nodes = {node.id: node for node in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("node IDs must be unique")
        if self.initial_node not in nodes:
            raise ValueError("initial_node is missing")
        for node in self.nodes:
            if len(set(node.transitions)) != len(node.transitions):
                raise ValueError("duplicate transition")
            if set(node.transitions) - nodes.keys():
                raise ValueError(f"unknown transition from {node.id}")
            if node.terminal and node.transitions:
                raise ValueError("terminal nodes cannot have outgoing transitions")
        reached = set()
        pending = [self.initial_node]
        while pending:
            current = pending.pop()
            if current not in reached:
                reached.add(current)
                pending.extend(nodes[current].transitions)
        if reached != nodes.keys():
            raise ValueError("all nodes must be reachable from initial_node")
        terminating = {node.id for node in self.nodes if node.terminal}
        while True:
            previous = terminating.copy()
            terminating.update(
                node.id for node in self.nodes if set(node.transitions) & terminating
            )
            if previous == terminating:
                break
        if terminating != nodes.keys():
            raise ValueError("each node must have a path to a terminal node")
        return self


class ContextConfig(ConfigModel):
    prune_node_ids: list[Identifier] = Field(default_factory=lambda: ["greeting"])
    remove_transition_tool_pairs: bool = True
    summarizer: SummarizerConfig = Field(default_factory=SummarizerConfig)


class LanguageConfig(ConfigModel):
    default_language: str = "en-IN"
    supported_languages: list[str] = Field(
        default_factory=lambda: ["en-IN", "hi-IN", "mr-IN", "te-IN"]
    )
    follow_caller_language: bool = True
    persist_requested_language: bool = True


class CallbackRoleConfig(ConfigModel):
    key: Identifier
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    enabled: bool = True


class BookablePersonConfig(ConfigModel):
    key: Identifier
    name: str = Field(min_length=1)
    roles: list[Identifier] = Field(min_length=1)
    calendar_integration_id: Identifier
    timezone: str = "UTC"
    enabled: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        return value


class CallbackSchedulingConfig(ConfigModel):
    enabled: bool = False
    slot_duration_minutes: int = Field(default=15, ge=5, le=120)
    minimum_notice_minutes: int = Field(default=0, ge=0, le=10080)
    roles: list[CallbackRoleConfig] = Field(default_factory=list)
    bookable_people: list[BookablePersonConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_roles(self):
        keys = {role.key for role in self.roles}
        if len(keys) != len(self.roles):
            raise ValueError("callback role keys must be unique")
        if any(role not in keys for person in self.bookable_people for role in person.roles):
            raise ValueError("bookable person references an unknown callback role")
        return self


class AgentConfig(ConfigModel):
    name: str = Field(min_length=1)
    persona: str = ""
    system_prompt: str = ""
    greeting: str = ""
    contact_variables: list[Identifier] = Field(default_factory=list)
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    flow: FlowConfig
    tool_bindings: dict[Identifier, ToolBinding] = Field(default_factory=dict)
    background_hooks: list[Identifier] = Field(default_factory=list)
    knowledge_base_ids: list[Identifier] = Field(default_factory=list)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    call_limits: CallLimits = Field(default_factory=CallLimits)
    context: ContextConfig = Field(default_factory=ContextConfig)
    classifier: ClassifierConfig = Field(default_factory=ClassifierConfig)
    callback_scheduling: CallbackSchedulingConfig = Field(default_factory=CallbackSchedulingConfig)
    pipeline_logs: Literal["inherit", "enabled", "disabled"] = "inherit"

    @model_validator(mode="after")
    def binding_references_exist(self):
        references = set(self.background_hooks)
        for node in self.flow.nodes:
            references.update(node.tool_bindings + node.entry_actions + node.exit_actions)
        if references - self.tool_bindings.keys():
            raise ValueError(
                f"unknown tool bindings: {sorted(references - self.tool_bindings.keys())}"
            )
        return self
