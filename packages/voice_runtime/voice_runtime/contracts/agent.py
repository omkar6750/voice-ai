"""Agent-owned graphs, prompts, exact tool bindings, and runtime settings."""

import math
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    Field,
    HttpUrl,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError
from voice_shared.contact_variables import normalize_contact_config
from voice_shared.prompt_templates import (
    TEMPORAL_KEYS,
    validate_config_templates,
)

from .base import ConfigModel, Identifier
from .cadence import ClassifierConfig, SummarizerConfig, lead_classifier_contract
from .knowledge import RetrievalConfig
from .prompt_references import tool_references
from .providers import (
    AudioConfig,
    CallLimits,
    LLMConfig,
    MainLLMConfig,
    STTConfig,
    TTSConfig,
    VADConfig,
)
from .tools import ToolBinding


class FlowMessageConfig(ConfigModel):
    """A context message intentionally added when entering a Pipecat flow node."""

    role: Literal["system", "developer", "user", "assistant"]
    content: str = ""


class FlowBranchConfig(ConfigModel):
    field: str = Field(min_length=1)
    cases: dict[str, Identifier] = Field(default_factory=dict)
    default: Identifier | None = None


class FlowFunctionConfig(ConfigModel):
    name: Identifier
    transition_only: bool = False
    description: str | None = None
    transition_to: Identifier | FlowBranchConfig | None = None

    @model_validator(mode="after")
    def validate_transition_only(self):
        if self.transition_only and (
            not self.description or not isinstance(self.transition_to, str)
        ):
            raise ValueError(
                "transition_only functions require a description and fixed transition_to"
            )
        if not self.transition_only and self.description is not None:
            raise ValueError("description is only supported for transition_only functions")
        if self.name == "classify_lead" and isinstance(self.transition_to, FlowBranchConfig):
            fields = lead_classifier_contract()["fields"]
            branch = self.transition_to
            if branch.field not in fields or set(branch.cases) - set(fields[branch.field]):
                raise ValueError(
                    "classify_lead routing requires a fixed output field and enum cases"
                )
        return self


class FactSlotConfig(ConfigModel):
    """Operator-declared, fixed-key values the caller can ask the agent to capture."""

    key: Identifier
    description: str = Field(min_length=1, max_length=500)
    value_type: Literal["string", "integer", "number", "boolean"] = "string"
    default_value: str | int | float | bool = ""
    enum: list[str | int | float | bool] | None = None
    minimum: float | None = None
    maximum: float | None = None
    nodes: list[Identifier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_constraints(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("fact slot minimum must not exceed maximum")
        if self.value_type not in {"integer", "number"} and (
            self.minimum is not None or self.maximum is not None
        ):
            raise ValueError("fact slot ranges require an integer or number value_type")
        if self.default_value != "":
            self.validate_value(self.default_value)
        if self.enum is not None and not self.enum:
            raise ValueError("fact slot enum must not be empty")
        if self.enum is not None:
            for value in self.enum:
                self.validate_value(value)
        return self

    def validate_value(self, value: Any) -> Any:
        valid_type = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
        }[self.value_type](value)
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"fact slot '{self.key}' must be finite")
        if not valid_type:
            raise ValueError(f"fact slot '{self.key}' expects {self.value_type}")
        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"fact slot '{self.key}' is below its minimum")
        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"fact slot '{self.key}' exceeds its maximum")
        if self.enum is not None and value not in self.enum:
            raise ValueError(f"fact slot '{self.key}' is outside its allowed values")
        return value


class FlowNodeConfig(ConfigModel):
    id: Identifier
    # Native Pipecat name: FlowManager sends this as the provider system instruction.
    role_message: str | None = None
    # Explicit context messages. Do not use these for node objectives that must
    # retain system-instruction priority across providers.
    task_messages: list[FlowMessageConfig] = Field(default_factory=list)
    functions: list[FlowFunctionConfig] = Field(default_factory=list)
    # Native Pipecat action names and payloads. The runtime validates these
    # again through Pipecat's FlowConfig before a call starts.
    pre_actions: list[dict[str, Any]] = Field(default_factory=list)
    post_actions: list[dict[str, Any]] = Field(default_factory=list)
    # Legacy fields are retained so existing published snapshots remain readable.
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
    global_functions: list[FlowFunctionConfig] = Field(default_factory=list)
    prompt_composition: Literal["node_only", "global_plus_node"] = "node_only"

    @field_validator("global_functions", mode="before")
    @classmethod
    def accept_legacy_global_function_names(cls, value):
        if isinstance(value, list):
            return [{"name": item} if isinstance(item, str) else item for item in value]
        return value

    @model_validator(mode="after")
    def valid_graph(self, info: ValidationInfo):
        nodes = {node.id: node for node in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError("node IDs must be unique")
        if self.initial_node not in nodes:
            raise ValueError("initial_node is missing")
        initial = nodes[self.initial_node]
        if (
            not (info.context or {}).get("read_legacy_config")
            and initial.respond_immediately
            and not any(
                message.role == "user" and message.content.strip()
                for message in initial.task_messages
            )
        ):
            raise ValidationError.from_exception_data(
                type(self).__name__,
                [
                    {
                        "type": PydanticCustomError(
                            "initial_user_task_required",
                            "Initial nodes that respond on entry require a nonempty user task message.",
                        ),
                        "loc": ("nodes", self.nodes.index(initial), "task_messages"),
                    }
                ],
            )
        for node in self.nodes:
            if len(set(node.transitions)) != len(node.transitions):
                raise ValueError("duplicate transition")
            if set(node.transitions) - nodes.keys():
                raise ValueError(f"unknown transition from {node.id}")
            if node.terminal and node.transitions:
                raise ValueError("terminal nodes cannot have outgoing transitions")
            if len({function.name for function in node.functions}) != len(node.functions):
                raise ValueError(f"duplicate function in node '{node.id}'")
            if set(node.tool_bindings) & {function.name for function in node.functions}:
                raise ValueError(f"duplicate tool binding in node '{node.id}'")
            for function in node.functions:
                if isinstance(function.transition_to, str):
                    targets = {function.transition_to}
                elif function.transition_to is not None:
                    targets = set(function.transition_to.cases.values())
                    if function.transition_to.default:
                        targets.add(function.transition_to.default)
                else:
                    targets = set()
                if targets - nodes.keys():
                    raise ValueError(
                        f"function '{function.name}' in node '{node.id}' targets an unknown node"
                    )
        for function in self.global_functions:
            if function.transition_only:
                raise ValueError("global functions cannot be transition_only")
            targets = set()
            if isinstance(function.transition_to, str):
                targets.add(function.transition_to)
            elif function.transition_to is not None:
                targets.update(function.transition_to.cases.values())
                if function.transition_to.default:
                    targets.add(function.transition_to.default)
            if targets - nodes.keys():
                raise ValueError(f"global function '{function.name}' targets an unknown node")
        if len({function.name for function in self.global_functions}) != len(self.global_functions):
            raise ValueError("duplicate global function")
        edges = {node.id: set(node.transitions) for node in self.nodes}
        for node in self.nodes:
            for function in node.functions:
                target = function.transition_to
                if isinstance(target, str):
                    edges[node.id].add(target)
                elif target is not None:
                    edges[node.id].update(target.cases.values())
                    if target.default:
                        edges[node.id].add(target.default)
            if node.terminal and edges[node.id]:
                raise ValueError("terminal nodes cannot have outgoing transitions")
        reached = set()
        pending = [self.initial_node]
        while pending:
            current = pending.pop()
            if current not in reached:
                reached.add(current)
                pending.extend(edges[current])
        if reached != nodes.keys():
            raise ValueError("all nodes must be reachable from initial_node")
        terminating = {node.id for node in self.nodes if node.terminal}
        while True:
            previous = terminating.copy()
            terminating.update(node.id for node in self.nodes if edges[node.id] & terminating)
            if previous == terminating:
                break
        if terminating != nodes.keys():
            raise ValueError("each node must have a path to a terminal node")
        return self


class ContextConfig(ConfigModel):
    summarizer: SummarizerConfig = Field(default_factory=SummarizerConfig)

    @model_validator(mode="before")
    @classmethod
    def drop_unsupported_pruning_controls(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            value.pop("prune_node_ids", None)
            value.pop("remove_transition_tool_pairs", None)
        return value


class LanguageConfig(ConfigModel):
    default_language: str = "en-IN"
    supported_languages: list[str] = Field(
        default_factory=lambda: ["en-IN", "hi-IN", "mr-IN", "te-IN"]
    )


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


class ComposerTemplateConfig(ConfigModel):
    system_prompt: str = Field(min_length=1, max_length=12000)
    required_urls: list[HttpUrl] = Field(default_factory=list)

    @field_validator("required_urls")
    @classmethod
    def secure_urls(cls, urls: list[HttpUrl]) -> list[HttpUrl]:
        if any(url.scheme != "https" or url.username or url.password for url in urls):
            raise ValueError("composer required URLs must be public HTTPS links")
        return urls


class ComposerConfig(ConfigModel):
    enabled: bool = False
    model: LLMConfig = Field(default_factory=lambda: LLMConfig(temperature=0.2, max_tokens=300))
    timeout_secs: float = Field(default=20, gt=0, le=60)
    templates: dict[Identifier, ComposerTemplateConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_templates(self):
        if self.enabled and not self.templates:
            raise ValueError("enabled composer requires at least one WhatsApp template prompt")
        return self


class AgentConfig(ConfigModel):
    @model_validator(mode="before")
    @classmethod
    def canonical_contact_variables(cls, value):
        return normalize_contact_config(value) if isinstance(value, dict) else value

    name: str = Field(min_length=1)
    system_prompt: str = ""
    # Deprecated compatibility input. The runtime folds this into the initial
    # node role_message; new configurations should put the opening in the flow.
    greeting: str = ""
    idle_reprompt_text: str = Field(default="Are you still there?", max_length=500)
    idle_reprompt_limit: int = Field(default=1, ge=0, le=5)
    filter_incomplete_user_turns: bool = False
    contact_variables: list[Identifier] = Field(default_factory=list)
    language: LanguageConfig = Field(default_factory=LanguageConfig)
    flow: FlowConfig
    fact_slots: list[FactSlotConfig] = Field(default_factory=list)
    tool_bindings: dict[Identifier, ToolBinding] = Field(default_factory=dict)
    background_hooks: list[Identifier] = Field(default_factory=list)
    knowledge_base_ids: list[Identifier] = Field(default_factory=list)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    credential_refs: dict[
        Literal[
            "stt", "llm", "llm_fallback", "tts", "classifier", "summarizer", "embedding", "composer"
        ],
        Identifier,
    ] = Field(default_factory=dict)
    llm: MainLLMConfig = Field(default_factory=MainLLMConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    call_limits: CallLimits = Field(default_factory=CallLimits)
    context: ContextConfig = Field(default_factory=ContextConfig)
    classifier: ClassifierConfig = Field(default_factory=ClassifierConfig)
    composer: ComposerConfig = Field(default_factory=ComposerConfig)
    callback_scheduling: CallbackSchedulingConfig = Field(default_factory=CallbackSchedulingConfig)
    pipeline_logs: Literal["inherit", "enabled", "disabled"] = "inherit"

    @model_validator(mode="after")
    def binding_references_exist(self):
        if set(self.composer.templates) - set(self.tool_bindings):
            raise ValueError("composer prompt references an unbound tool")
        references = set(self.background_hooks)
        for node_index, node in enumerate(self.flow.nodes):
            references.update(node.tool_bindings + node.entry_actions + node.exit_actions)
            for function in node.functions:
                if function.name == "change_node":
                    raise ValueError("change_node is replaced by native transition functions")
                if not function.transition_only:
                    references.add(function.name)
            for action in [*node.pre_actions, *node.post_actions]:
                action_type = action.get("type")
                if action_type not in {"tts_say", "end_conversation", "function"}:
                    raise ValueError(f"unsupported Pipecat action type: {action_type}")
                if action_type == "function":
                    handler = action.get("handler")
                    if not isinstance(handler, str) or not handler:
                        raise ValueError("function actions require a handler")
                    references.add(handler)
            available = (
                set(node.tool_bindings)
                | {function.name for function in self.flow.global_functions}
                | {function.name for function in node.functions}
                | {f"go_to_{target}" for target in node.transitions}
                | {
                    f"record_{slot.key}"
                    for slot in self.fact_slots
                    if not slot.nodes or node.id in slot.nodes
                }
            )
            prompt_fields = [
                ("prompt", node.prompt),
                ("role_prompt", node.role_prompt),
                ("role_message", node.role_message),
            ]
            prompt_fields.extend(
                (f"task_messages.{index}", message.content)
                for index, message in enumerate(node.task_messages)
            )
            errors = []
            for field, text in prompt_fields:
                unbound = tool_references(text or "") - available
                if not unbound:
                    continue
                loc = ("flow", "nodes", node_index)
                if field.startswith("task_messages."):
                    loc += ("task_messages", int(field.split(".")[1]), "content")
                else:
                    loc += (field,)
                scoped_fact = unbound & {f"record_{slot.key}" for slot in self.fact_slots}
                code = "fact_tool_unavailable" if scoped_fact else "unbound_prompt_tool"
                errors.append(
                    {
                        "type": PydanticCustomError(
                            code, "unbound prompt tool references: tool unavailable in this node"
                        ),
                        "loc": loc,
                    }
                )
            if errors:
                raise ValidationError.from_exception_data(type(self).__name__, errors)
        if references - self.tool_bindings.keys():
            raise ValueError(
                f"unknown tool bindings: {sorted(references - self.tool_bindings.keys())}"
            )
        global_refs = {function.name for function in self.flow.global_functions}
        if global_refs - self.tool_bindings.keys():
            raise ValueError(
                f"unknown global tool bindings: {sorted(global_refs - self.tool_bindings.keys())}"
            )
        node_refs = {name for node in self.flow.nodes for name in node.tool_bindings}
        node_refs.update(
            function.name
            for node in self.flow.nodes
            for function in node.functions
            if not function.transition_only
        )
        if global_refs & node_refs:
            raise ValueError("a global function cannot also be bound to an individual node")
        node_function_refs = {
            function.name
            for node in self.flow.nodes
            for function in node.functions
            if not function.transition_only
        }
        if node_function_refs & global_refs:
            raise ValueError("a function cannot be both node-scoped and global")
        if node_function_refs - self.tool_bindings.keys():
            raise ValueError(
                f"unknown tool bindings: {sorted(node_function_refs - self.tool_bindings.keys())}"
            )
        slot_keys = [slot.key for slot in self.fact_slots]
        if len(set(slot_keys)) != len(slot_keys):
            raise ValueError("fact slot keys must be unique")
        node_ids = {node.id for node in self.flow.nodes}
        for slot in self.fact_slots:
            if set(slot.nodes) - node_ids:
                raise ValueError(f"fact slot '{slot.key}' references an unknown node")
        generated_fact_tools = {f"record_{key}" for key in slot_keys}
        generated_transition_tools = {
            f"go_to_{target}" for node in self.flow.nodes for target in node.transitions
        }
        collisions = (generated_fact_tools | generated_transition_tools) & set(self.tool_bindings)
        collisions |= generated_fact_tools & global_refs
        if collisions:
            raise ValueError(
                f"generated flow functions collide with tool bindings: {sorted(collisions)}"
            )
        return self

    @model_validator(mode="after")
    def validate_prompt_templates(self, info: ValidationInfo):
        if (info.context or {}).get("read_legacy_config"):
            return self
        cfg = self.model_dump(mode="python")
        collisions = {s.key for s in self.fact_slots} & (
            set(self.contact_variables) | TEMPORAL_KEYS
        )
        if collisions:
            raise ValueError(f"Fact keys collide with prompt variables: {sorted(collisions)}")
        validate_config_templates(cfg)
        return self

    @model_validator(mode="before")
    @classmethod
    def ignore_legacy_persona(cls, value):
        """Keep historical configs readable after persona was removed."""
        if isinstance(value, dict) and "persona" in value:
            value = dict(value)
            value.pop("persona", None)
        return value
