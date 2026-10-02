import importlib.util
import json
from pathlib import Path

from voice_runtime.execution.pipecat_flow import compile_pipecat_flow
from voice_shared.compiler import compile_flow_json

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "focused_builder", ROOT / "scripts/build_elevated_box_focused_local.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def config():
    base = json.loads(
        (ROOT / "docs/plan/elevated-box-local-native.json").read_text(encoding="utf-8")
    )
    bindings = dict(base["tool_bindings"])
    bindings.pop("change_node", None)
    bindings.pop("end_call", None)
    bindings[builder.KB_TOOL] = next(iter(bindings.values()))
    return builder.build_config(base, bindings, "reference-kb")


def test_scoped_prompts_and_tool_permissions():
    cfg = config()
    nodes = {n["id"]: n for n in cfg["flow"]["nodes"]}
    assert len(nodes) == 8
    assert "USD" not in cfg["system_prompt"]
    assert "8k" not in nodes["greeting"]["role_message"]
    assert "15%" not in nodes["greeting"]["role_message"]
    assert "USD 8k-15k" in nodes["discovery_and_qualify"]["role_message"]
    assert "15%" in nodes["hot_followup"]["role_message"]
    assert not cfg["flow"]["global_functions"]
    for key, n in nodes.items():
        names = {f["name"] for f in n["functions"]}
        assert "change_node" not in names
        if "whatsapp_template_dialtone_followup" in names:
            assert key in {"hot_followup", "warm_nurture"}
        if "book_callback" in names:
            assert key == "callback_scheduling"
        assert all(m["role"] == "system" for m in n["task_messages"])
        assert len(cfg["system_prompt"]) + len(n["role_message"]) < 4500
    assert nodes["closing"]["terminal"]
    assert nodes["closing"]["post_actions"] == [{"type": "end_conversation"}]
    assert not nodes["closing"]["functions"]


def test_explicit_classification_and_complete_routing():
    cfg = config()
    classifier = cfg["classifier"]
    assert not classifier["node_entries"] and not classifier["node_exits"]
    assert classifier.get("every_n_exchanges") is None
    assert classifier.get("routing_policy") is None
    discovery = next(n for n in cfg["flow"]["nodes"] if n["id"] == "discovery_and_qualify")
    branch = next(f for f in discovery["functions"] if f["name"] == "classify_lead")[
        "transition_to"
    ]
    assert branch["field"] == "classification_key"
    assert len(branch["cases"]) == 27
    assert branch["cases"]["hot|strong_fit|receptive"] == "hot_followup"
    assert branch["cases"]["cold|strong_fit|resistant"] == "cold_check"
    assert branch["cases"]["hot|poor_fit|receptive"] == "fit_clarification"
    assert branch["cases"]["warm|possible_fit|hesitant"] == "warm_nurture"
    assert branch.get("default") is None


def test_real_flow_compiler_accepts_all_paths():
    cfg = config()

    async def handler(flow_manager, **params):
        from pipecat.flows import TRANSITION_IN_YAML

        return {}, TRANSITION_IN_YAML

    compiled = compile_flow_json(cfg)
    compile_pipecat_flow(
        {**cfg, "_compiled_flow": compiled},
        handlers={name: handler for name in cfg["tool_bindings"]},
    )
