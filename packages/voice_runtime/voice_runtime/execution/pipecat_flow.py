"""Compile the saved graph into Pipecat's validated declarative Flow."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pipecat.flows import Flow
from pipecat.flows import FlowConfig as PipecatFlowConfig


def compile_pipecat_flow(
    snapshot: dict[str, Any], *, handlers: Mapping[str, Any] | None = None
) -> Flow:
    """Build Pipecat nodes and transition-only tools from a published snapshot.

    Registered application tools keep their versioned JSON Schema and are
    attached as FlowsFunctionSchema objects by NativePipelineHost. Edges are
    represented by Pipecat transition-only functions, so the model chooses a
    named edge instead of supplying an arbitrary destination to change_node.
    """
    if snapshot.get("_compiled_flow") is not None:
        return Flow(
            PipecatFlowConfig.model_validate(snapshot["_compiled_flow"]), handlers=handlers or {}
        )
    app_flow = snapshot["flow"]
    nodes: dict[str, dict[str, Any]] = {}
    for node in app_flow["nodes"]:
        legacy_prompt = (node.get("prompt") or "").strip()
        role_parts = [
            part.strip()
            for part in (
                (
                    snapshot.get("system_prompt")
                    if app_flow.get("prompt_composition", "node_only") == "global_plus_node"
                    else None
                ),
                node.get("role_message") or node.get("role_prompt"),
            )
            if isinstance(part, str) and part.strip()
        ]
        if legacy_prompt:
            if "change_node" in legacy_prompt and node.get("transitions"):
                legacy_prompt = legacy_prompt.replace(
                    "change_node", "appropriate transition function"
                )
                targets = ", ".join(_transition_name(target) for target in node["transitions"])
                role_parts.append(
                    f"Use the transition function matching the destination: {targets}."
                )
            role_parts.append(f"Current node objective:\n{legacy_prompt}")
        if node["id"] == app_flow["initial_node"]:
            legacy_greeting = (snapshot.get("greeting") or "").strip()
            if legacy_greeting:
                role_parts.append(f"Opening message from legacy config:\n{legacy_greeting}")
            elif not legacy_prompt and not node.get("role_message") and not node.get("role_prompt"):
                role_parts.append("Open with a brief, natural greeting, then ask how you can help.")
        if node.get("terminal"):
            role_parts.append(
                "Deliver the terminal response now. Do not restart the conversation, "
                "greet the caller, ask discovery questions, or continue the flow."
            )
        if not role_parts:
            role_parts.append(
                "You are a helpful voice assistant. Continue naturally and answer the caller."
            )

        # Explicit function configuration owns its name. Allowed transitions can
        # describe the same edge without exposing a second tool to Pipecat.
        explicit_names = {
            function["name"] if isinstance(function, dict) else function.name
            for function in node.get("functions", [])
        }
        functions = []
        for target in node.get("transitions", []):
            if _transition_name(target) in explicit_names:
                continue
            functions.append(
                {
                    "name": _transition_name(target),
                    "transition_only": True,
                    "description": f"Continue the conversation at {target.replace('_', ' ')}.",
                    "transition_to": target,
                }
            )
        functions.extend(
            function.model_dump(mode="json", exclude_none=True)
            if hasattr(function, "model_dump")
            else deepcopy(function)
            for function in node.get("functions", [])
        )
        for function in functions:
            if isinstance(function.get("transition_to"), dict):
                branch = dict(function["transition_to"])
                branch["cases"] = {
                    str(value).lower() if isinstance(value, bool) else str(value): target
                    for value, target in branch["cases"].items()
                }
                function["transition_to"] = branch if branch["cases"] else branch.get("default")
        pre_actions = deepcopy(node.get("pre_actions", []))
        post_actions = deepcopy(node.get("post_actions", []))
        for phase, binding_keys, target_actions in (
            ("entry", node.get("entry_actions", []), pre_actions),
            ("exit", node.get("exit_actions", []), post_actions),
        ):
            target_actions.extend(
                {
                    "type": "function",
                    "handler": "_run_configured_node_action",
                    "phase": phase,
                    "node_id": node["id"],
                    "binding_key": binding_key,
                }
                for binding_key in binding_keys
            )
        for phase, actions in (("entry", pre_actions), ("exit", post_actions)):
            for action in actions:
                if action.get("type") != "function" or not action.get("handler"):
                    continue
                binding_key = action["handler"]
                action["handler"] = "_run_configured_node_action"
                action["binding_key"] = binding_key
                action.setdefault("node_id", node["id"])
                action.setdefault("phase", phase)

        nodes[node["id"]] = {
            "role_message": "\n\n".join(dict.fromkeys(role_parts)),
            "task_messages": [
                {"role": message["role"], "content": message["content"]}
                for message in node.get("task_messages", [])
            ],
            "functions": functions,
            "pre_actions": pre_actions,
            "post_actions": post_actions,
            "context_strategy": node.get("context_strategy", "append"),
            "respond_immediately": (
                True
                if node["id"] == app_flow["initial_node"]
                and (snapshot.get("greeting") or "").strip()
                else node.get("respond_immediately", True)
            ),
        }

    global_functions = [
        {"name": function} if isinstance(function, str) else deepcopy(function)
        for function in app_flow.get("global_functions", [])
    ]
    for function in global_functions:
        branch = function.get("transition_to")
        if isinstance(branch, dict) and not branch.get("cases"):
            function["transition_to"] = branch.get("default")
    config = PipecatFlowConfig.model_validate(
        {
            "initial_node": app_flow["initial_node"],
            "nodes": nodes,
            "global_functions": global_functions,
        }
    )
    # All functions in this compiler output are transition_only, so no Python
    # handler namespace is required. Pipecat validates targets and builds the
    # corresponding NodeConfig objects here.
    return Flow(config, handlers=handlers or {})


def _transition_name(target: str) -> str:
    return f"go_to_{target}"
