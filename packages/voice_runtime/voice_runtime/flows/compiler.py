"""Compile a validated graph without importing provider SDKs or performing actions."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from voice_runtime.contracts import AgentConfig


@dataclass(frozen=True)
class CompiledFlow:
    initial_node: str
    nodes: dict[str, dict[str, Any]]
    transitions: dict[str, frozenset[str]]

    def transition(self, source: str, destination: str) -> dict[str, Any]:
        if destination not in self.transitions.get(source, frozenset()):
            raise ValueError(f"transition {source!r} -> {destination!r} is not allowed")
        return self.nodes[destination]


def compile_flow(config: AgentConfig, tools: Mapping[str, Any] | None = None) -> CompiledFlow:
    """Bindings resolve to reviewed runtime functions, never executable config strings.

    Returned node dictionaries follow the installed demo's role_message/task_messages
    convention. Action binding IDs are kept separate for the runtime action executor.
    """
    config = AgentConfig.model_validate(config.model_dump())
    resolved = tools if tools is not None else {}
    referenced = {key for node in config.flow.nodes for key in node.tool_bindings}
    if referenced - resolved.keys():
        raise ValueError(f"unresolved tool bindings: {sorted(referenced - resolved.keys())}")
    nodes = {}
    for node in config.flow.nodes:
        prompt = node.prompt
        if config.flow.prompt_composition == "global_plus_node":
            prompt = "\n\n".join(
                part for part in [config.persona, config.system_prompt, prompt] if part
            )
        nodes[node.id] = {
            "name": node.id,
            "role_message": prompt,
            "task_messages": [],
            "functions": [resolved[key] for key in node.tool_bindings],
            "respond_immediately": node.respond_immediately,
        }
    return CompiledFlow(
        config.flow.initial_node,
        nodes,
        {node.id: frozenset(node.transitions) for node in config.flow.nodes},
    )
