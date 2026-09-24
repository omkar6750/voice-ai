import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  Plus,
  Save,
} from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useApi } from "../app/api";
import {
  Button,
  Field,
  Input,
  Island,
  Notice,
  Select,
  Status,
  Textarea,
} from "../components/ui";

type Agent = { id: string; name: string; active_version_id: string | null };
type Node = {
  id: string;
  prompt: string;
  transitions: string[];
  tool_bindings: string[];
  entry_actions: string[];
  exit_actions: string[];
  respond_immediately: boolean;
  terminal: boolean;
};
type Config = {
  name: string;
  persona: string;
  system_prompt: string;
  greeting: string;
  language: {
    default_language: string;
    supported_languages: string[];
    follow_caller_language: boolean;
  };
  flow: {
    initial_node: string;
    prompt_composition: "node_only" | "global_plus_node";
    nodes: Node[];
  };
  tool_bindings: Record<string, { tool_id: string; tool_version_id: string }>;
  knowledge_base_ids: string[];
  retrieval: {
    top_k: number;
    keyword_weight: number;
    vector_weight: number;
    result_budget_tokens: number;
    timeout_secs: number;
  };
  stt: { provider: "sarvam"; model: string };
  llm: {
    provider: "groq";
    model: string;
    temperature: number;
    max_tokens: number;
    top_p: number | null;
    reasoning_effort: string;
  };
  tts: {
    provider: "sarvam" | "cartesia";
    model: string;
    voice: string;
    language: string;
    pace: number;
  };
  audio: {
    sample_rate: number;
    channels: number;
    encoding: string;
    frame_ms: number;
  };
  vad: {
    confidence: number;
    start_secs: number;
    stop_secs: number;
    min_volume: number;
  };
  call_limits: {
    max_duration_secs: number;
    idle_timeout_secs: number;
    interruptions_enabled: boolean;
  };
  context: {
    prune_node_ids: string[];
    remove_transition_tool_pairs: boolean;
    summarizer: {
      enabled: boolean;
      unsummarized_messages: number;
      compaction_threshold: number;
      hard_ceiling: number;
      target_ratio: number;
      output_budget_tokens: number;
    };
  };
  classifier: {
    enabled: boolean;
    node_exits: string[];
    confidence_threshold: number;
    every_n_exchanges: number | null;
    on_finalization: boolean;
  };
  pipeline_logs: "inherit" | "enabled" | "disabled";
};
type Version = {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  config: Config;
  note: string | null;
};
type KnowledgeBase = { id: string; name: string };

const tabs = [
  "Prompts",
  "Flow",
  "Models & voice",
  "Audio & calls",
  "Context & analysis",
  "Knowledge & tools",
] as const;
type Tab = (typeof tabs)[number];

export function AgentsPage() {
  const api = useApi();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [versions, setVersions] = useState<Record<string, Version[]>>({});
  const [name, setName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ agents: Agent[] }>("/agents")
      .then(async (data) => {
        setAgents(data.agents);
        const entries = await Promise.all(
          data.agents.map(
            async (agent) =>
              [
                agent.id,
                (
                  await api<{ versions: Version[] }>(
                    `/agents/${agent.id}/versions`,
                  )
                ).versions,
              ] as const,
          ),
        );
        setVersions(Object.fromEntries(entries));
      })
      .catch((cause) =>
        setError(
          cause instanceof Error ? cause.message : "Could not load agents",
        ),
      );
  }, [api]);
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const clean = name.trim();
      const config = {
        name: clean,
        persona: "",
        system_prompt: "",
        flow: {
          initial_node: "greeting",
          nodes: [{ id: "greeting", prompt: "", terminal: true }],
        },
      };
      const created = await api<{ agent_id: string; version_id: string }>(
        "/agents",
        { method: "POST", body: JSON.stringify({ name: clean, config }) },
      );
      navigate(`/agents/${created.agent_id}/versions/${created.version_id}`);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create agent",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-primary">Authoring</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Agents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Draft, publish and activate voice configurations.
          </p>
        </div>
        <Button onClick={() => setShowCreate(!showCreate)}>
          <Plus size={16} /> New agent
        </Button>
      </div>
      {error && <Notice text={error} error />}
      {showCreate && (
        <Island
          title="Create agent"
          description="Starts a minimal draft with one greeting node."
        >
          <form
            onSubmit={create}
            className="flex max-w-xl flex-col gap-3 sm:flex-row sm:items-end"
          >
            <div className="min-w-0 flex-1">
              <Field label="Agent name">
                <Input
                  autoFocus
                  required
                  maxLength={120}
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. Sales assistant"
                />
              </Field>
            </div>
            <Button disabled={busy || !name.trim()} type="submit">
              Create draft
            </Button>
          </form>
        </Island>
      )}
      <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        {agents.length === 0 ? (
          <p className="p-8 text-sm text-muted-foreground">
            No agents yet. Create a draft to start.
          </p>
        ) : (
          agents.map((agent) => {
            const list = versions[agent.id] ?? [];
            const latest = list.at(-1);
            const target = list.find((v) => v.status === "draft") ?? latest;
            return (
              <div
                key={agent.id}
                className="flex flex-wrap items-center justify-between gap-4 border-b border-border px-5 py-4 last:border-b-0"
              >
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold">{agent.name}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {list.length} version{list.length === 1 ? "" : "s"} ·{" "}
                    {agent.active_version_id
                      ? "Active version set"
                      : "No active version"}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  {latest && <Status value={latest.status} />}
                  {target && (
                    <Link
                      className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
                      to={`/agents/${agent.id}/versions/${target.id}`}
                    >
                      Open <ChevronRight size={16} />
                    </Link>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export function AgentLanding() {
  const { agentId } = useParams();
  const api = useApi();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  useEffect(() => {
    if (!agentId) return;
    api<{ versions: Version[] }>(`/agents/${agentId}/versions`)
      .then(({ versions }) => {
        const target = versions.find((item) => item.status === "draft") ?? versions.at(-1);
        if (target) navigate(`/agents/${agentId}/versions/${target.id}`, { replace: true });
        else setError("This agent has no versions.");
      })
      .catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load agent"));
  }, [agentId, api, navigate]);
  return error ? <Notice text={error} error /> : <p className="text-sm text-muted-foreground">Opening agent…</p>;
}

export function AgentEditor() {
  const { agentId, versionId } = useParams();
  const api = useApi();
  const navigate = useNavigate();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [base, setBase] = useState<Version | null>(null);
  const [draft, setDraft] = useState<Config | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const tab: Tab = tabs.find((item) => item === requestedTab) ?? "Prompts";
  const [nodeId, setNodeId] = useState("");
  const [knowledge, setKnowledge] = useState<KnowledgeBase[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dirty = useMemo(
    () =>
      base && draft
        ? JSON.stringify(base.config) !== JSON.stringify(draft)
        : false,
    [base, draft],
  );
  useEffect(() => {
    if (!agentId || !versionId) return;
    Promise.all([
      api<{ agents: Agent[] }>("/agents"),
      api<{ versions: Version[] }>(`/agents/${agentId}/versions`),
      api<{ knowledge_bases: KnowledgeBase[] }>("/knowledge-bases"),
    ])
      .then(([agentsData, versionsData, kbData]) => {
        setAgent(agentsData.agents.find((item) => item.id === agentId) ?? null);
        setVersions(versionsData.versions);
        const selected =
          versionsData.versions.find((item) => item.id === versionId) ?? null;
        setBase(selected);
        setDraft(selected ? structuredClone(selected.config) : null);
        setNodeId(selected?.config.flow.nodes[0]?.id ?? "");
        setKnowledge(kbData.knowledge_bases);
      })
      .catch((cause) =>
        setError(
          cause instanceof Error ? cause.message : "Could not load agent",
        ),
      );
  }, [api, agentId, versionId]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function update(fn: (current: Config) => Config) {
    setDraft((current) => (current ? fn(current) : current));
    setNotice("");
    setError("");
  }
  async function save() {
    if (!base || !draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const saved = await api<{ revision: number; config: Config }>(
        `/agent-versions/${base.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            revision: base.revision,
            config: draft,
            note: base.note,
          }),
        },
      );
      setBase({ ...base, revision: saved.revision, config: saved.config });
      setDraft(structuredClone(saved.config));
      setNotice("Draft saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }
  async function publish() {
    if (!base || dirty) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/agent-versions/${base.id}/publish`, {
        method: "POST",
        body: JSON.stringify({ revision: base.revision }),
      });
      setBase({ ...base, status: "published" });
      setNotice("Version published. Activate it to use it for new calls.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Publish failed");
    } finally {
      setBusy(false);
    }
  }
  async function activate() {
    if (!base || !agent) return;
    setBusy(true);
    setError("");
    try {
      await api(`/agents/${agent.id}/activate`, {
        method: "POST",
        body: JSON.stringify({ version_id: base.id }),
      });
      setAgent({ ...agent, active_version_id: base.id });
      setNotice("Version activated for new calls.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Activation failed");
    } finally {
      setBusy(false);
    }
  }
  async function clone() {
    if (!base || dirty) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ id?: string; version_id?: string }>(
        `/agent-versions/${base.id}/clone`,
        { method: "POST", body: JSON.stringify({ revision: base.revision }) },
      );
      navigate(`/agents/${agentId}/versions/${result.id ?? result.version_id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Clone failed");
    } finally {
      setBusy(false);
    }
  }
  if (!base || !draft || !agent)
    return (
      <div className="space-y-4">
        <Link className="text-sm text-primary" to="/agents">
          ← Agents
        </Link>
        {error ? (
          <Notice text={error} error />
        ) : (
          <p className="text-sm text-muted-foreground">Loading agent…</p>
        )}
      </div>
    );
  const config = draft;
  const readOnly = base.status !== "draft";
  const node =
    draft.flow.nodes.find((item) => item.id === nodeId) ?? draft.flow.nodes[0];
  const updateNode = (changes: Partial<Node>) =>
    update((current) => ({
      ...current,
      flow: {
        ...current.flow,
        nodes: current.flow.nodes.map((item) =>
          item.id === node.id ? { ...item, ...changes } : item,
        ),
      },
    }));
  function addNode() {
    const id = `node_${config.flow.nodes.length + 1}`;
    const next: Node = {
      id,
      prompt: "",
      transitions: [],
      tool_bindings: [],
      entry_actions: [],
      exit_actions: [],
      respond_immediately: true,
      terminal: true,
    };
    update((current) => ({
      ...current,
      flow: {
        ...current.flow,
        nodes: [
          ...current.flow.nodes.map((item) =>
            item.id === node.id
              ? {
                  ...item,
                  terminal: false,
                  transitions: [...item.transitions, id],
                }
              : item,
          ),
          next,
        ],
      },
    }));
    setNodeId(id);
  }
  const fieldGrid = "grid gap-4 md:grid-cols-2";
  return (
    <div className="space-y-5">
      <Link
        to="/agents"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
        onClick={(event) => {
          if (dirty && !window.confirm("Discard unsaved changes?"))
            event.preventDefault();
        }}
      >
        <ArrowLeft size={15} /> Agents
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-primary">
            Agent / Version {base.version}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">
              {agent.name}
            </h1>
            <Status value={base.status} />
            {agent.active_version_id === base.id && (
              <span className="rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-accent-foreground">
                Active
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Revision {base.revision}
            {dirty ? " · Unsaved changes" : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {readOnly ? (
            <>
              <Button variant="secondary" disabled={busy} onClick={clone}>
                Clone draft
              </Button>
              <Button
                disabled={busy || agent.active_version_id === base.id}
                onClick={activate}
              >
                <Check size={16} /> Activate
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="secondary"
                disabled={busy || dirty}
                onClick={publish}
              >
                Publish
              </Button>
              <Button disabled={busy || !dirty} onClick={save}>
                <Save size={16} /> Save draft
              </Button>
            </>
          )}
        </div>
      </div>
      {error && <Notice text={error} error />}
      {notice && <Notice text={notice} />}
      {base.status === "draft" && (
        <Notice text="Settings save to this version. The current live call bridge uses prompts, node bindings, initial node and duration; remaining runtime settings need call-path wiring." />
      )}
      {versions.length > 1 && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>Versions:</span>
          {versions.map((item) => (
            <Link
              key={item.id}
              to={`/agents/${agentId}/versions/${item.id}`}
              onClick={(event) => {
                if (dirty && !window.confirm("Discard unsaved changes?"))
                  event.preventDefault();
              }}
              className={`rounded-md px-2 py-1 ${item.id === base.id ? "bg-accent text-accent-foreground" : "hover:bg-secondary"}`}
            >
              v{item.version} {item.status}
            </Link>
          ))}
        </div>
      )}
      <nav
        aria-label="Agent settings"
        className="flex gap-1 overflow-x-auto border-b border-border pb-2"
      >
        {tabs.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setSearchParams({ tab: item })}
            className={`shrink-0 rounded-md px-3 py-2 text-sm font-medium transition-colors ${tab === item ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground"}`}
          >
            {item}
          </button>
        ))}
      </nav>
      {readOnly && tab === "Flow" && (
        <nav aria-label="Published flow nodes" className="flex flex-wrap gap-2">
          {draft.flow.nodes.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setNodeId(item.id)}
              className={`rounded-md px-3 py-2 text-sm ${item.id === node.id ? "bg-accent font-medium text-accent-foreground" : "bg-card text-muted-foreground hover:bg-secondary"}`}
            >
              {item.id}
            </button>
          ))}
        </nav>
      )}
      <fieldset
        disabled={readOnly || busy}
        className="space-y-5 disabled:opacity-80"
      >
        {tab === "Prompts" && (
          <>
            <Island
              title="Identity and opening"
              description="The agent's role and first spoken response."
            >
              <div className={fieldGrid}>
                <Field label="Display name">
                  <Input
                    value={draft.name}
                    onChange={(e) =>
                      update((c) => ({ ...c, name: e.target.value }))
                    }
                  />
                </Field>
                <Field label="Persona">
                  <Input
                    value={draft.persona}
                    onChange={(e) =>
                      update((c) => ({ ...c, persona: e.target.value }))
                    }
                  />
                </Field>
              </div>
              <div className="mt-4">
                <Field
                  label="Greeting"
                  hint="Opening text in agent configuration. A flow may generate the spoken greeting dynamically."
                >
                  <Textarea
                    className="min-h-24"
                    value={draft.greeting}
                    onChange={(e) =>
                      update((c) => ({ ...c, greeting: e.target.value }))
                    }
                  />
                </Field>
              </div>
            </Island>
            <Island
              title="System instruction"
              description="Global behavior and safety rules. Prompt composition below determines whether node prompts replace or extend it."
            >
              <Field label="Instruction">
                <Textarea
                  className="min-h-72 font-mono text-sm"
                  value={draft.system_prompt}
                  onChange={(e) =>
                    update((c) => ({ ...c, system_prompt: e.target.value }))
                  }
                />
              </Field>
              <div className="mt-4 max-w-sm">
                <Field label="Prompt composition">
                  <Select
                    value={draft.flow.prompt_composition}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        flow: {
                          ...c.flow,
                          prompt_composition: e.target
                            .value as Config["flow"]["prompt_composition"],
                        },
                      }))
                    }
                  >
                    <option value="node_only">
                      Node prompt replaces global
                    </option>
                    <option value="global_plus_node">
                      Global plus node prompt
                    </option>
                  </Select>
                </Field>
              </div>
            </Island>
          </>
        )}
        {tab === "Flow" && (
          <Island
            title="Dialogue flow"
            description="Select a node to edit its prompt, transitions and allowed tools."
            action={
              <Button variant="secondary" onClick={addNode} type="button">
                <Plus size={15} /> Add node
              </Button>
            }
          >
            <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="space-y-1 border-b border-border pb-4 lg:border-b-0 lg:border-r lg:pb-0 lg:pr-4">
                {draft.flow.nodes.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setNodeId(item.id)}
                    className={`flex w-full items-center justify-between rounded-md px-3 py-2.5 text-left text-sm ${item.id === node.id ? "bg-accent font-medium text-accent-foreground" : "hover:bg-secondary"}`}
                  >
                    <span className="truncate">{item.id}</span>
                    {item.id === draft.flow.initial_node ? (
                      <span className="text-xs text-muted-foreground">
                        Start
                      </span>
                    ) : (
                      <ChevronRight size={14} />
                    )}
                  </button>
                ))}
              </div>
              <div className="space-y-4">
                <div className={fieldGrid}>
                  <Field label="Node ID">
                    <Input value={node.id} disabled />
                  </Field>
                  <Field label="Initial node">
                    <Select
                      value={draft.flow.initial_node}
                      onChange={(e) =>
                        update((c) => ({
                          ...c,
                          flow: { ...c.flow, initial_node: e.target.value },
                        }))
                      }
                    >
                      {draft.flow.nodes.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.id}
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                <Field label="Node prompt">
                  <Textarea
                    className="min-h-48"
                    value={node.prompt}
                    onChange={(e) => updateNode({ prompt: e.target.value })}
                  />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="mb-2 text-sm font-medium">Next nodes</p>
                    <div className="space-y-2">
                      {draft.flow.nodes
                        .filter((item) => item.id !== node.id)
                        .map((item) => (
                          <label
                            key={item.id}
                            className="flex items-center gap-2 text-sm"
                          >
                            <input
                              type="checkbox"
                              className="accent-primary"
                              checked={node.transitions.includes(item.id)}
                              disabled={node.terminal}
                              onChange={(e) =>
                                updateNode({
                                  transitions: e.target.checked
                                    ? [...node.transitions, item.id]
                                    : node.transitions.filter(
                                        (x) => x !== item.id,
                                      ),
                                })
                              }
                            />
                            {item.id}
                          </label>
                        ))}
                    </div>
                  </div>
                  <div>
                    <p className="mb-2 text-sm font-medium">Allowed tools</p>
                    <div className="space-y-2">
                      {Object.keys(draft.tool_bindings).length ? (
                        Object.keys(draft.tool_bindings).map((key) => (
                          <label
                            key={key}
                            className="flex items-center gap-2 text-sm"
                          >
                            <input
                              type="checkbox"
                              className="accent-primary"
                              checked={node.tool_bindings.includes(key)}
                              onChange={(e) =>
                                updateNode({
                                  tool_bindings: e.target.checked
                                    ? [...node.tool_bindings, key]
                                    : node.tool_bindings.filter(
                                        (x) => x !== key,
                                      ),
                                })
                              }
                            />
                            {key}
                          </label>
                        ))
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          No pinned tool bindings.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-primary"
                    checked={node.terminal}
                    onChange={(e) =>
                      updateNode({
                        terminal: e.target.checked,
                        transitions: e.target.checked ? [] : node.transitions,
                      })
                    }
                  />
                  Terminal node
                </label>
              </div>
            </div>
          </Island>
        )}
        {tab === "Models & voice" && (
          <>
            <Island
              title="Conversation model"
              description="STT and LLM settings. Provider credentials are configured on the server."
            >
              <div className={fieldGrid}>
                <Field label="Speech recognition">
                  <Input
                    value={`${draft.stt.provider} / ${draft.stt.model}`}
                    disabled
                  />
                </Field>
                <Field label="LLM model">
                  <Input
                    value={draft.llm.model}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        llm: { ...c.llm, model: e.target.value },
                      }))
                    }
                  />
                </Field>
                <Field label="Max output tokens">
                  <Input
                    type="number"
                    min={1}
                    value={draft.llm.max_tokens}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        llm: { ...c.llm, max_tokens: Number(e.target.value) },
                      }))
                    }
                  />
                </Field>
                <Field label="Temperature">
                  <Input
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={draft.llm.temperature}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        llm: { ...c.llm, temperature: Number(e.target.value) },
                      }))
                    }
                  />
                </Field>
              </div>
            </Island>
            <Island
              title="Voice output"
              description="Set the TTS voice and language used by this agent."
            >
              <div className={fieldGrid}>
                <Field label="Provider">
                  <Select
                    value={draft.tts.provider}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        tts: {
                          ...c.tts,
                          provider: e.target.value as "sarvam" | "cartesia",
                          model:
                            e.target.value === "sarvam"
                              ? "bulbul:v3"
                              : "sonic-3",
                          voice: e.target.value === "sarvam" ? "ritu" : "",
                        },
                      }))
                    }
                  >
                    <option value="sarvam">Sarvam</option>
                    <option value="cartesia">Cartesia</option>
                  </Select>
                </Field>
                <Field label="Model">
                  <Input
                    value={draft.tts.model}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        tts: { ...c.tts, model: e.target.value },
                      }))
                    }
                  />
                </Field>
                <Field label="Voice ID">
                  <Input
                    value={draft.tts.voice}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        tts: { ...c.tts, voice: e.target.value },
                      }))
                    }
                  />
                </Field>
                <Field label="Language">
                  <Input
                    value={draft.tts.language}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        tts: { ...c.tts, language: e.target.value },
                      }))
                    }
                  />
                </Field>
              </div>
            </Island>
          </>
        )}
        {tab === "Audio & calls" && (
          <>
            <Island
              title="Audio path"
              description="Configured PCM format. Live call bridge still uses tested script constants."
            >
              <div className={fieldGrid}>
                <Field label="Sample rate">
                  <Select
                    value={draft.audio.sample_rate}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        audio: {
                          ...c.audio,
                          sample_rate: Number(e.target.value),
                        },
                      }))
                    }
                  >
                    <option value="8000">8 kHz</option>
                    <option value="16000">16 kHz</option>
                  </Select>
                </Field>
                <Field label="Frame size">
                  <Input
                    disabled
                    value={`${draft.audio.frame_ms} ms · mono ${draft.audio.encoding}`}
                  />
                </Field>
              </div>
            </Island>
            <Island
              title="Voice activity and limits"
              description="VAD thresholds, interruptions and call time limits."
            >
              <div className={fieldGrid}>
                <Field label="VAD confidence">
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={draft.vad.confidence}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        vad: { ...c.vad, confidence: Number(e.target.value) },
                      }))
                    }
                  />
                </Field>
                <Field label="Minimum volume">
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={draft.vad.min_volume}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        vad: { ...c.vad, min_volume: Number(e.target.value) },
                      }))
                    }
                  />
                </Field>
                <Field label="Speech start (seconds)">
                  <Input
                    type="number"
                    min={0.01}
                    step={0.05}
                    value={draft.vad.start_secs}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        vad: { ...c.vad, start_secs: Number(e.target.value) },
                      }))
                    }
                  />
                </Field>
                <Field label="Speech stop (seconds)">
                  <Input
                    type="number"
                    min={0.01}
                    step={0.05}
                    value={draft.vad.stop_secs}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        vad: { ...c.vad, stop_secs: Number(e.target.value) },
                      }))
                    }
                  />
                </Field>
                <Field label="Maximum call (seconds)">
                  <Input
                    type="number"
                    min={1}
                    value={draft.call_limits.max_duration_secs}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        call_limits: {
                          ...c.call_limits,
                          max_duration_secs: Number(e.target.value),
                        },
                      }))
                    }
                  />
                </Field>
                <Field label="Idle timeout (seconds)">
                  <Input
                    type="number"
                    min={1}
                    value={draft.call_limits.idle_timeout_secs}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        call_limits: {
                          ...c.call_limits,
                          idle_timeout_secs: Number(e.target.value),
                        },
                      }))
                    }
                  />
                </Field>
              </div>
              <label className="mt-5 flex items-center gap-2 text-sm font-medium">
                <input
                  type="checkbox"
                  className="accent-primary"
                  checked={draft.call_limits.interruptions_enabled}
                  onChange={(e) =>
                    update((c) => ({
                      ...c,
                      call_limits: {
                        ...c.call_limits,
                        interruptions_enabled: e.target.checked,
                      },
                    }))
                  }
                />
                Allow caller interruptions
              </label>
            </Island>
          </>
        )}
        {tab === "Context & analysis" && (
          <>
            <Island
              title="Language and context"
              description="Language follows caller when enabled. Context compaction remains a runtime integration task."
            >
              <div className={fieldGrid}>
                <Field label="Default language">
                  <Input
                    value={draft.language.default_language}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        language: {
                          ...c.language,
                          default_language: e.target.value,
                        },
                      }))
                    }
                  />
                </Field>
                <Field
                  label="Supported languages"
                  hint="Comma-separated language codes."
                >
                  <Input
                    value={draft.language.supported_languages.join(", ")}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        language: {
                          ...c.language,
                          supported_languages: e.target.value
                            .split(",")
                            .map((x) => x.trim())
                            .filter(Boolean),
                        },
                      }))
                    }
                  />
                </Field>
              </div>
              <label className="mt-4 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="accent-primary"
                  checked={draft.language.follow_caller_language}
                  onChange={(e) =>
                    update((c) => ({
                      ...c,
                      language: {
                        ...c.language,
                        follow_caller_language: e.target.checked,
                      },
                    }))
                  }
                />
                Follow caller language
              </label>
            </Island>
            <Island
              title="Analysis cadence"
              description="Classifier and summarizer policies are stored with this version."
            >
              <div className={fieldGrid}>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-primary"
                    checked={draft.classifier.enabled}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        classifier: {
                          ...c.classifier,
                          enabled: e.target.checked,
                        },
                      }))
                    }
                  />
                  Enable classifier
                </label>
                <Field label="Minimum confidence">
                  <Input
                    type="number"
                    min={0}
                    max={1}
                    step={0.05}
                    value={draft.classifier.confidence_threshold}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        classifier: {
                          ...c.classifier,
                          confidence_threshold: Number(e.target.value),
                        },
                      }))
                    }
                  />
                </Field>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="accent-primary"
                    checked={draft.context.summarizer.enabled}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        context: {
                          ...c.context,
                          summarizer: {
                            ...c.context.summarizer,
                            enabled: e.target.checked,
                          },
                        },
                      }))
                    }
                  />
                  Enable summarizer
                </label>
                <Field label="Unsummarized messages">
                  <Input
                    type="number"
                    min={1}
                    value={draft.context.summarizer.unsummarized_messages}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        context: {
                          ...c.context,
                          summarizer: {
                            ...c.context.summarizer,
                            unsummarized_messages: Number(e.target.value),
                          },
                        },
                      }))
                    }
                  />
                </Field>
              </div>
            </Island>
          </>
        )}
        {tab === "Knowledge & tools" && (
          <>
            <Island
              title="Knowledge bases"
              description="Agent links to mutable bases; retrieval settings belong to this agent version."
            >
              <div className="space-y-2">
                {knowledge.length ? (
                  knowledge.map((item) => (
                    <label
                      key={item.id}
                      className="flex items-center gap-2 text-sm"
                    >
                      <input
                        type="checkbox"
                        className="accent-primary"
                        checked={draft.knowledge_base_ids.includes(item.id)}
                        onChange={(e) =>
                          update((c) => ({
                            ...c,
                            knowledge_base_ids: e.target.checked
                              ? [...c.knowledge_base_ids, item.id]
                              : c.knowledge_base_ids.filter(
                                  (x) => x !== item.id,
                                ),
                          }))
                        }
                      />
                      {item.name}
                    </label>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No knowledge bases available.
                  </p>
                )}
              </div>
              <div className={`mt-5 ${fieldGrid}`}>
                <Field label="Top results">
                  <Input
                    type="number"
                    min={1}
                    max={100}
                    value={draft.retrieval.top_k}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        retrieval: {
                          ...c.retrieval,
                          top_k: Number(e.target.value),
                        },
                      }))
                    }
                  />
                </Field>
                <Field label="Result token budget">
                  <Input
                    type="number"
                    min={1}
                    value={draft.retrieval.result_budget_tokens}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        retrieval: {
                          ...c.retrieval,
                          result_budget_tokens: Number(e.target.value),
                        },
                      }))
                    }
                  />
                </Field>
              </div>
            </Island>
            <Island
              title="Pinned tools and logging"
              description="Versions are pinned at agent level; each flow node enables selected binding keys."
            >
              <div className="space-y-2">
                {Object.entries(draft.tool_bindings).length ? (
                  Object.entries(draft.tool_bindings).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex justify-between gap-4 border-b border-border py-2 text-sm last:border-0"
                    >
                      <span className="font-medium">{key}</span>
                      <span
                        className="truncate font-mono text-xs text-muted-foreground"
                        title={value.tool_version_id}
                      >
                        {value.tool_version_id.slice(0, 12)}
                      </span>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No tool versions pinned.
                  </p>
                )}
              </div>
              <div className="mt-5 max-w-sm">
                <Field label="Pipeline log capture">
                  <Select
                    value={draft.pipeline_logs}
                    onChange={(e) =>
                      update((c) => ({
                        ...c,
                        pipeline_logs: e.target
                          .value as Config["pipeline_logs"],
                      }))
                    }
                  >
                    <option value="inherit">Inherit workspace default</option>
                    <option value="enabled">Enabled</option>
                    <option value="disabled">Disabled</option>
                  </Select>
                </Field>
              </div>
            </Island>
          </>
        )}
      </fieldset>
      {!readOnly && (
        <div className="flex justify-end border-t border-border pt-4">
          <Button disabled={busy || !dirty} onClick={save}>
            <Save size={16} /> Save draft <ArrowRight size={15} />
          </Button>
        </div>
      )}
    </div>
  );
}
