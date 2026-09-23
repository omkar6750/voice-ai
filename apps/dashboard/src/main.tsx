import { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Provider = { provider: string; slots: string[]; models: string[] };
type Timeline = {
  run: { id: string; status: string };
  call: { id: string; status: string } | null;
  exchanges: { id: string; sequence: number; origin: string; status: string }[];
  messages: { id: string; exchange_id: string; role: string; content: string; interrupted: boolean; created_at: string }[];
  spans: { id: string; exchange_id: string | null; name: string; category: string; status: string; started_at: string; ended_at: string | null }[];
  tools: { id: string; exchange_id: string | null; binding_key: string; status: string; arguments: object; result: object }[];
};

const defaultWorkspace = JSON.stringify(
  {
    recording_retention_days: 7,
    pipeline_log_retention_days: 7,
    pipeline_logs_enabled: false,
    automatic_callbacks_enabled: false,
    callback_due_window_minutes: 15,
  },
  null,
  2,
);

function App() {
  const [token, setToken] = useState(sessionStorage.getItem("voice-operator-token") ?? "");
  const [tab, setTab] = useState<"runtime" | "knowledge" | "traces">("runtime");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [workspace, setWorkspace] = useState(defaultWorkspace);
  const [workspaceRevision, setWorkspaceRevision] = useState(1);
  const [runId, setRunId] = useState("");
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [notice, setNotice] = useState("Set operator token, then load control plane.");

  const headers = useMemo(
    () => ({ Authorization: `Bearer ${token}`, "Content-Type": "application/json" }),
    [token],
  );

  async function request(path: string, init: RequestInit = {}) {
    const response = await fetch(path, { ...init, headers: { ...headers, ...init.headers } });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail ?? `Request failed: ${response.status}`);
    return response.status === 204 ? null : response.json();
  }

  async function loadRuntime() {
    try {
      const [providerData, workspaceData] = await Promise.all([request("/api/providers"), request("/api/workspace")]);
      setProviders(providerData.providers);
      setWorkspace(JSON.stringify(workspaceData.config, null, 2));
      setWorkspaceRevision(workspaceData.revision);
      setNotice("Control plane loaded.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not load control plane.");
    }
  }

  useEffect(() => {
    if (token) void loadRuntime();
  }, []);

  function saveToken(event: FormEvent) {
    event.preventDefault();
    sessionStorage.setItem("voice-operator-token", token);
    void loadRuntime();
  }

  async function saveWorkspace(event: FormEvent) {
    event.preventDefault();
    try {
      const data = await request("/api/workspace", {
        method: "PATCH",
        body: JSON.stringify({ revision: workspaceRevision, config: JSON.parse(workspace) }),
      });
      setWorkspaceRevision(data.revision);
      setWorkspace(JSON.stringify(data.config, null, 2));
      setNotice("Workspace settings saved.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Workspace save failed.");
    }
  }

  async function loadTimeline(event: FormEvent) {
    event.preventDefault();
    try {
      setTimeline(await request(`/api/runs/${runId}/timeline`));
      setNotice("Trace loaded.");
    } catch (error) {
      setTimeline(null);
      setNotice(error instanceof Error ? error.message : "Trace load failed.");
    }
  }

  return <main className="shell">
    <header>
      <div><p className="eyebrow">Voice runtime</p><h1>Control plane</h1></div>
      <form className="token" onSubmit={saveToken}>
        <input aria-label="Operator token" value={token} onChange={(event) => setToken(event.target.value)} placeholder="Operator token" type="password" />
        <button>Connect</button>
      </form>
    </header>
    <p className="notice">{notice}</p>
    <nav aria-label="Dashboard sections">
      {(["runtime", "knowledge", "traces"] as const).map((item) => <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)}>{item}</button>)}
    </nav>
    {tab === "runtime" && <section className="grid">
      <article><h2>Configured providers</h2>{providers.length === 0 ? <p>Connect to load provider catalog.</p> : providers.map((provider) => <div className="provider" key={provider.provider}><strong>{provider.provider}</strong><span>{provider.slots.join(" · ")}</span><code>{provider.models.join(", ")}</code></div>)}</article>
      <article><h2>Workspace settings</h2><p>Retention, call logging, callbacks. Contact timezone stays on contact.</p><form onSubmit={saveWorkspace}><textarea value={workspace} onChange={(event) => setWorkspace(event.target.value)} spellCheck="false" /><button>Save revision {workspaceRevision}</button></form></article>
      <article className="wide"><h2>Agent config</h2><p>Draft/publish APIs ready. UI editor next slice. Runtime config generated from <code>/api/config-schema</code>, no hand-maintained dashboard schema.</p><p>Tool versions bind to draft agent version. Nodes enable binding names. Published versions immutable.</p></article>
    </section>}
    {tab === "knowledge" && <section className="grid"><article className="wide"><h2>Mutable knowledge bases</h2><p>API supports paste, TXT and Markdown source builds with Gemini embeddings. Chunk rebuild keeps current searchable chunks until replacement succeeds.</p><p>Knowledge retrieval evidence belongs in tool invocation trace, not separate message archive.</p></article></section>}
    {tab === "traces" && <section className="trace"><form onSubmit={loadTimeline}><input value={runId} onChange={(event) => setRunId(event.target.value)} placeholder="Run ID" /><button>Load trace</button></form>{timeline && <><h2>{timeline.run.status} · {timeline.call?.status ?? "no call"}</h2><div className="timeline">{timeline.spans.map((span) => <div className="span" key={span.id}><b>{span.category}</b><span>{span.name}</span><small>{new Date(span.started_at).toLocaleTimeString()} → {span.ended_at ? new Date(span.ended_at).toLocaleTimeString() : "running"}</small></div>)}</div><h2>Transcript</h2>{timeline.messages.map((message) => <p className={`message ${message.role}`} key={message.id}><b>{message.role}</b> {message.content} {message.interrupted && <em>interrupted</em>}</p>)}</>}</section>}
  </main>;
}

createRoot(document.getElementById("root")!).render(<App />);
