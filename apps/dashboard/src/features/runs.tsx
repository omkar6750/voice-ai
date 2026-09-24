import { ArrowLeft, CalendarClock, Radio, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useApi } from "../app/api";
import { Button, Island, Notice, Status } from "../components/ui";

type Run = {
  id: string;
  channel: string;
  agent_version_id: string;
  contact_id: string | null;
  status: string;
  created_at: string;
};
type Message = {
  id: string;
  exchange_id: string;
  role: string;
  content: string;
  interrupted: boolean;
  created_at: string;
};
type Span = {
  id: string;
  exchange_id: string | null;
  name: string;
  category: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  ttfb_ms: number | null;
  ttfa_ms: number | null;
};
type Tool = {
  id: string;
  exchange_id: string | null;
  binding_key: string;
  status: string;
  arguments: unknown;
  result: unknown;
};
type Timeline = {
  run: { id: string; status: string; agent_id: string; agent_version_id: string };
  call: { id: string; status: string } | null;
  exchanges: { id: string; sequence: number; origin: string; status: string }[];
  messages: Message[];
  spans: Span[];
  tools: Tool[];
};

const timestamp = (value: string) => new Date(value).toLocaleString();
const elapsed = (value: number | null) =>
  value == null
    ? "Unknown"
    : value < 1000
      ? `${Math.round(value)} ms`
      : `${(value / 1000).toFixed(2)} s`;

export function RunsPage() {
  const api = useApi();
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ runs: Run[] }>("/runs")
      .then((data) => setRuns(data.runs))
      .catch((cause) =>
        setError(
          cause instanceof Error ? cause.message : "Could not load runs",
        ),
      );
  }, [api]);
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-medium text-primary">Execution</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every browser or telephony execution has a run. A call is attached
          when telephony is involved.
        </p>
      </div>
      {error && <Notice text={error} error />}
      <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
        <div className="hidden grid-cols-[minmax(0,1fr)_130px_150px_120px] gap-4 border-b border-border bg-secondary/50 px-5 py-3 text-xs font-semibold text-muted-foreground sm:grid">
          <span>Run</span>
          <span>Channel</span>
          <span>Created</span>
          <span>Status</span>
        </div>
        {runs.length === 0 ? (
          <p className="p-8 text-sm text-muted-foreground">No runs recorded.</p>
        ) : (
          runs.map((run) => (
            <Link
              key={run.id}
              to={`/runs/${run.id}`}
              className="grid gap-2 border-b border-border px-5 py-4 text-sm last:border-0 hover:bg-white sm:grid-cols-[minmax(0,1fr)_130px_150px_120px] sm:items-center sm:gap-4"
            >
              <span className="min-w-0 truncate font-medium">{run.id}</span>
              <span className="capitalize text-muted-foreground">
                {run.channel}
              </span>
              <span className="text-xs text-muted-foreground">
                {timestamp(run.created_at)}
              </span>
              <span>
                <Status value={run.status} />
              </span>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}

export function RunDetailPage() {
  const { runId } = useParams();
  const api = useApi();
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"Conversation" | "Operations">("Conversation");
  const load = useCallback(() => {
    if (!runId) return;
    api<Timeline>(`/runs/${runId}/timeline`)
      .then(setTimeline)
      .catch((cause) =>
        setError(
          cause instanceof Error ? cause.message : "Could not load timeline",
        ),
      );
  }, [api, runId]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (
      !timeline ||
      !["queued", "claimed", "running"].includes(timeline.run.status)
    )
      return;
    const id = window.setInterval(load, 3000);
    return () => window.clearInterval(id);
  }, [timeline?.run.status, load]);
  const operations = timeline
    ? [
        ...timeline.spans.map((span) => ({
          id: span.id,
          kind: "span" as const,
          span,
        })),
        ...timeline.tools.map((tool) => ({
          id: tool.id,
          kind: "tool" as const,
          tool,
        })),
      ]
    : [];
  return (
    <div className="space-y-5">
      <Link
        to="/runs"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
      >
        <ArrowLeft size={15} /> Runs
      </Link>
      {error && <Notice text={error} error />}
      {!timeline ? (
        <p className="text-sm text-muted-foreground">Loading run…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-primary">Run details</p>
              <h1 className="mt-1 break-all text-xl font-semibold tracking-tight sm:text-2xl">
                {runId}
              </h1>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Status value={timeline.run.status} />
                <Link
                  className="text-sm font-medium text-primary hover:underline"
                  to={`/agents/${timeline.run.agent_id}/versions/${timeline.run.agent_version_id}`}
                >
                  Agent configuration
                </Link>
                {timeline.call && (
                  <span className="text-sm text-muted-foreground">
                    Call {timeline.call.id.slice(0, 8)} · {timeline.call.status}
                  </span>
                )}
              </div>
            </div>
            <Button variant="secondary" onClick={load}>
              <RefreshCw size={15} /> Refresh
            </Button>
          </div>
          {["queued", "claimed", "running"].includes(timeline.run.status) && (
            <Notice text="Run is active. This page refreshes every 3 seconds. Live listening needs the monitoring stream described in RFC-0013." />
          )}
          {!timeline.messages.length && !timeline.spans.length && (
            <Notice text="No finalized transcript or operation evidence is stored for this run. Call status alone does not prove a complete trace." />
          )}
          <nav
            aria-label="Run views"
            className="flex gap-1 border-b border-border pb-2"
          >
            {(["Conversation", "Operations"] as const).map((item) => (
              <button
                key={item}
                type="button"
                className={`rounded-md px-3 py-2 text-sm font-medium ${tab === item ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-secondary"}`}
                onClick={() => setTab(item)}
              >
                {item}
              </button>
            ))}
          </nav>
          {tab === "Conversation" && (
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
              <Island
                title="Transcript"
                description="Finalized messages grouped by exchange."
              >
                <div className="space-y-5">
                  {timeline.exchanges.length ? (
                    timeline.exchanges.map((exchange) => (
                      <div
                        key={exchange.id}
                        className="border-b border-border pb-5 last:border-0 last:pb-0"
                      >
                        <div className="mb-3 flex items-center gap-2 text-xs font-medium text-muted-foreground">
                          <CalendarClock size={14} /> Exchange{" "}
                          {exchange.sequence} · {exchange.origin}
                        </div>
                        <div className="space-y-3">
                          {timeline.messages
                            .filter(
                              (message) => message.exchange_id === exchange.id,
                            )
                            .map((message) => (
                              <div
                                key={message.id}
                                className={`max-w-2xl rounded-lg px-4 py-3 text-sm leading-6 ${message.role === "assistant" ? "ml-auto bg-accent text-foreground" : "bg-white"}`}
                              >
                                <div className="mb-1 flex items-center justify-between gap-2">
                                  <span className="text-xs font-semibold capitalize text-muted-foreground">
                                    {message.role}
                                  </span>
                                  <time className="text-xs text-muted-foreground">
                                    {new Date(
                                      message.created_at,
                                    ).toLocaleTimeString()}
                                  </time>
                                </div>
                                <p className="whitespace-pre-wrap">
                                  {message.content}
                                </p>
                                {message.interrupted && (
                                  <span className="mt-2 inline-block text-xs text-amber-700">
                                    Interrupted
                                  </span>
                                )}
                              </div>
                            ))}
                        </div>
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Transcript unavailable.
                    </p>
                  )}
                </div>
              </Island>
              <div className="space-y-5">
                <Island title="Call" description="Transport and trace status.">
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Channel</span>
                      <span>{timeline.call ? "Telephony" : "Browser"}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Exchanges</span>
                      <span>{timeline.exchanges.length}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Operations</span>
                      <span>{timeline.spans.length}</span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">Tools</span>
                      <span>{timeline.tools.length}</span>
                    </div>
                  </div>
                </Island>
                <Island
                  title="Monitoring"
                  description="Live audio requires a run-scoped stream."
                >
                  <div className="flex items-start gap-3 text-sm text-muted-foreground">
                    <Radio size={17} className="mt-0.5 shrink-0" />
                    <p>
                      Listen-only audio and live logs are planned in RFC-0013.
                      Stored timeline remains available here.
                    </p>
                  </div>
                </Island>
              </div>
            </div>
          )}
          {tab === "Operations" && (
            <Island
              title="Operations"
              description="Recorded timing and tool evidence. Overlapping operations are not added into a total."
            >
              <div className="space-y-2">
                {operations.length ? (
                  operations.map((item) =>
                    item.kind === "span" ? (
                      <div
                        key={item.id}
                        className="grid gap-2 rounded-md border border-border bg-white px-4 py-3 text-sm sm:grid-cols-[120px_minmax(0,1fr)_100px] sm:items-center"
                      >
                        <span className="font-medium capitalize text-muted-foreground">
                          {item.span.category}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {item.span.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {item.span.provider && `${item.span.provider} · `}
                            {item.span.model ?? ""}
                            {item.span.ttfb_ms != null &&
                              ` · TTFT ${elapsed(item.span.ttfb_ms)}`}
                            {item.span.ttfa_ms != null &&
                              ` · First audio ${elapsed(item.span.ttfa_ms)}`}
                          </p>
                        </div>
                        <span className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                          {elapsed(item.span.duration_ms)}
                        </span>
                      </div>
                    ) : (
                      <div
                        key={item.id}
                        className="rounded-md border border-border bg-white px-4 py-3 text-sm"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="font-medium">
                            Tool · {item.tool.binding_key}
                          </p>
                          <Status value={item.tool.status} />
                        </div>
                        <details className="mt-2 text-xs text-muted-foreground">
                          <summary className="cursor-pointer">
                            Arguments and result
                          </summary>
                          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-md bg-secondary p-3 font-mono">
                            {JSON.stringify(
                              {
                                arguments: item.tool.arguments,
                                result: item.tool.result,
                              },
                              null,
                              2,
                            )}
                          </pre>
                        </details>
                      </div>
                    ),
                  )
                ) : (
                  <p className="text-sm text-muted-foreground">
                    No operations stored.
                  </p>
                )}
              </div>
            </Island>
          )}
        </>
      )}
    </div>
  );
}
