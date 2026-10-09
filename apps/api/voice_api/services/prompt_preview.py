"""Read-only preview using the same compiler and resolver as node entry."""

from voice_runtime.contracts import AgentConfig
from voice_runtime.contracts.prompt_references import compile_tool_references
from voice_runtime.execution.temporal import resolve_local_time_context
from voice_shared.compiler import compile_flow_json
from voice_shared.prompt_templates import initialize_facts, render_node, variable_types


def preview_prompt(config: AgentConfig, node_id: str, contact: dict, facts: dict) -> dict:
    cfg = config.model_dump(mode="python")
    if set(contact) - set(config.contact_variables):
        raise ValueError("Sample contact values must be exposed contact variables")
    slots = {s.key: s for s in config.fact_slots}
    if set(facts) - slots.keys():
        raise ValueError("Sample facts must be declared conversation facts")
    state = resolve_local_time_context(contact.get("timezone"))
    state.update(dict.fromkeys(config.contact_variables, ""))
    state.update({key: "" if value is None else value for key, value in contact.items()})
    initialize_facts(state, cfg["fact_slots"])
    for key, value in facts.items():
        state[key] = value if value == "" else slots[key].validate_value(value)
    node = compile_flow_json(cfg)["nodes"].get(node_id)
    if node is None:
        raise ValueError("Unknown preview node")
    functions = {f["name"] for f in node["functions"]}
    functions.update(f["name"] for f in cfg["flow"]["global_functions"])
    functions.update(next(n.tool_bindings for n in config.flow.nodes if n.id == node_id))
    functions.update(
        f"record_{s.key}" for s in config.fact_slots if not s.nodes or node_id in s.nodes
    )
    node["role_message"] = compile_tool_references(node["role_message"], functions)
    for message in node["task_messages"]:
        message["content"] = compile_tool_references(message["content"], functions)
    sources = {k: {"kind": "contact"} for k in config.contact_variables}
    sources.update(
        {s.key: {"kind": "sample" if s.key in facts else "default"} for s in config.fact_slots}
    )
    rendered, records = render_node(node, state, variable_types(cfg), sources)
    return {
        "node_id": node_id,
        "rendered": {
            k: rendered[k] for k in ("role_message", "task_messages", "pre_actions", "post_actions")
        },
        "resolution": records,
        "refresh": "node_entry",
    }
