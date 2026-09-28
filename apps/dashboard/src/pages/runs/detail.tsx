import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Activity, ArrowLeft, FileAudio, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { useApi, useOperatorToken } from "@/app/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { isActive, duration, stamp } from "./model";
import { StatusBadge } from "./status";
import { Waterfall } from "./waterfall";
import { Transcript } from "./transcript";
import { Inspector } from "./inspector";
import type {
  Artifact,
  RunDetail,
  RunSummary,
  Selection,
  Timeline,
} from "./types";

function AudioTrack({ artifact }: { artifact: Artifact }) {
  const token = useOperatorToken();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  async function load() {
    setBusy(true);
    try {
      const response = await fetch(
        "/api/v1/artifacts/" + artifact.id + "/file",
        {
          headers: { Authorization: "Bearer " + token },
        },
      );
      if (!response.ok)
        throw new Error("Audio unavailable (" + response.status + ")");
      setUrl(URL.createObjectURL(await response.blob()));
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not load audio",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-1 py-2">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="capitalize">
          {artifact.kind === "input"
            ? "Caller"
            : artifact.kind === "output"
              ? "Agent"
              : "Mixed"}{" "}
          audio
        </span>
        <span className="text-xs text-muted-foreground">
          {Math.round(artifact.size_bytes / 1024)} KB
        </span>
      </div>
      {artifact.deleted_at ? (
        <p className="text-xs text-muted-foreground">Recording expired.</p>
      ) : url ? (
        <audio controls preload="metadata" src={url} className="w-full" />
      ) : (
        <Button variant="outline" size="sm" disabled={busy} onClick={load}>
          {busy ? (
            <Spinner data-icon="inline-start" />
          ) : (
            <FileAudio data-icon="inline-start" />
          )}{" "}
          {busy ? "Loading…" : "Load recording"}
        </Button>
      )}
    </div>
  );
}

function PipelineDebugLog({ artifact }: { artifact: Artifact }) {
  const token = useOperatorToken();
  const [content, setContent] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try {
      const response = await fetch(
        "/api/v1/artifacts/" + artifact.id + "/file",
        {
          headers: { Authorization: "Bearer " + token },
        },
      );
      if (!response.ok)
        throw new Error("Pipeline log unavailable (" + response.status + ")");
      setContent(await response.text());
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not load pipeline log",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Pipeline debug log</CardTitle>
        <CardDescription>
          Timestamped provider, VAD, turn, interruption, and playback events.
          Open only when the structured diagnosis needs more detail.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {artifact.deleted_at ? (
          <p className="text-sm text-muted-foreground">Debug log expired.</p>
        ) : content === null ? (
          <Button variant="outline" size="sm" disabled={busy} onClick={load}>
            {busy ? (
              <Spinner data-icon="inline-start" />
            ) : (
              <Activity data-icon="inline-start" />
            )}
            {busy ? "Loading…" : "Load pipeline log"}
          </Button>
        ) : (
          <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap break-all">
            {content || "The pipeline log is empty."}
          </pre>
        )}
      </CardContent>
    </Card>
  );
}

export function RunDetailPage() {
  const { runId } = useParams();
  const api = useApi();
  const [searchParams, setSearchParams] = useSearchParams();
  const lens =
    searchParams.get("lens") === "transcript" ? "transcript" : "waterfall";
  const [run, setRun] = useState<RunDetail | null>(null);
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selection, setSelection] = useState<Selection>({ kind: "run" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const currentRun = useRef(runId);
  const lastToast = useRef("");
  currentRun.current = runId;
  const select = (value: Selection) => {
    setSelection(value);
  };
  const load = useCallback(
    async (notify = false) => {
      if (!runId) return;
      try {
        const [detail, evidence, catalog, files] = await Promise.all([
          api<RunDetail>("/runs/" + runId),
          api<Timeline>("/runs/" + runId + "/timeline"),
          api<{ runs: RunSummary[] }>("/runs"),
          api<{ artifacts: Artifact[] }>("/runs/" + runId + "/artifacts"),
        ]);
        if (currentRun.current !== runId) return;
        setRun(detail);
        setTimeline(evidence);
        setRuns(catalog.runs);
        setArtifacts(files.artifacts);
        setError("");
        lastToast.current = "";
        if (notify) toast.success("Run refreshed");
      } catch (cause) {
        if (currentRun.current !== runId) return;
        const message =
          cause instanceof Error ? cause.message : "Could not load run";
        setError(message);
        if (notify || lastToast.current !== message) toast.error(message);
        lastToast.current = message;
      } finally {
        if (currentRun.current === runId) setLoading(false);
      }
    },
    [api, runId],
  );
  useEffect(() => {
    setSelection({ kind: "run" });
    setRun(null);
    setTimeline(null);
    setArtifacts([]);
    setLoading(true);
    void load();
  }, [runId, load]);
  useEffect(() => {
    if (!run || !isActive(run.status)) return;
    const timer = window.setInterval(() => {
      void load();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [run?.status, load]);
  const recorded = artifacts.filter((item) => item.kind !== "pipeline_log");
  const pipelineLog = artifacts.find((item) => item.kind === "pipeline_log");
  const durationMs =
    run?.started_at && run.ended_at
      ? Date.parse(run.ended_at) - Date.parse(run.started_at)
      : null;
  const ttft =
    timeline?.spans
      .filter((span) => span.ttfb_ms != null)
      .map((span) => span.ttfb_ms!) ?? [];
  const llmSpans =
    timeline?.spans.filter((span) => span.category === "llm") ?? [];
  const usageSpans = llmSpans.filter(
    (span) =>
      span.total_tokens != null ||
      (span.prompt_tokens != null && span.completion_tokens != null),
  );
  const inputTokens = usageSpans.reduce(
    (sum, span) => sum + (span.prompt_tokens ?? 0),
    0,
  );
  const outputTokens = usageSpans.reduce(
    (sum, span) => sum + (span.completion_tokens ?? 0),
    0,
  );
  const totalTokens = usageSpans.reduce(
    (sum, span) =>
      sum +
      (span.total_tokens ?? span.prompt_tokens! + span.completion_tokens!),
    0,
  );
  const derivedTotals = usageSpans.some((span) => span.total_tokens == null);
  const tokenCoverage =
    usageSpans.length === llmSpans.length ? "" : " (partial)";
  return (
    <div className="flex min-w-0 flex-col lg:flex-row">
      <aside className="hidden w-48 shrink-0 border-r bg-card lg:block">
        <div className="sticky top-0 flex max-h-[calc(100svh-3rem)] flex-col">
          <div className="border-b p-3 text-xs font-medium">
            Recent runs · {runs.length}
          </div>
          <nav
            aria-label="Switch run"
            className="flex min-h-0 flex-col gap-1 overflow-y-auto p-2"
          >
            {runs.map((item) => (
              <Link
                key={item.id}
                to={"/runs/" + item.id}
                className={
                  "flex flex-col gap-1 rounded-md p-2 text-xs hover:bg-accent " +
                  (item.id === runId ? "bg-accent" : "")
                }
              >
                <span className="truncate font-medium">
                  {item.contact_name ?? item.id.slice(0, 12)}
                </span>
                <span className="flex items-center justify-between gap-1">
                  <span className="truncate text-muted-foreground">
                    {item.channel}
                  </span>
                  <StatusBadge status={item.status} />
                </span>
              </Link>
            ))}
          </nav>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 lg:p-5">
        <Link
          className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"
          to="/runs"
        >
          <ArrowLeft className="size-4" /> All runs
        </Link>
        {loading && !run ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-10 w-2/3" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-72 w-full" />
          </div>
        ) : error && !run ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>Run unavailable</EmptyTitle>
              <EmptyDescription>{error}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : run && timeline ? (
          <>
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {run.channel} run · {run.id.slice(0, 12)}
                </p>
                <h1 className="truncate text-xl font-semibold">
                  {run.contact_snapshot?.name
                    ? String(run.contact_snapshot.name)
                    : "Conversation"}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <StatusBadge status={run.status} />
                  <span className="text-xs text-muted-foreground">
                    {stamp(run.started_at ?? run.created_at)}
                  </span>
                  <Link
                    className="text-xs font-medium text-primary hover:underline"
                    to={
                      "/agents/" +
                      timeline.run.agent_id +
                      "/versions/" +
                      timeline.run.agent_version_id
                    }
                  >
                    Agent version
                  </Link>
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => select({ kind: "prompt" })}
                >
                  System prompt
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void load(true)}
                >
                  <RefreshCw data-icon="inline-start" /> Refresh
                </Button>
              </div>
            </header>
            <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-y py-3 text-xs">
              <span>
                Duration <strong>{duration(durationMs)}</strong>
              </span>
              <span>
                Exchanges <strong>{timeline.exchanges.length}</strong>
              </span>
              {timeline.run.evidence_complete === false && (
                <Badge variant="destructive">
                  Evidence incomplete · replay required
                </Badge>
              )}
              <span>
                Provider operations <strong>{timeline.spans.length}</strong>
              </span>
              <span>
                LLM calls <strong>{llmSpans.length}</strong>
              </span>
              <span>
                Conversation LLM tokens{" "}
                <strong>
                  {usageSpans.length
                    ? `${totalTokens}${tokenCoverage}`
                    : "Not recorded"}
                </strong>
                {usageSpans.length > 0 && (
                  <span className="text-muted-foreground">
                    {" "}
                    · {inputTokens} in / {outputTokens} out ·{" "}
                    {usageSpans.length}/{llmSpans.length} measured
                    {derivedTotals ? " · some totals derived" : ""}
                  </span>
                )}
              </span>
              <span>
                Tools <strong>{timeline.tools.length}</strong>
              </span>
              <span>
                Avg first token{" "}
                <strong>
                  {ttft.length
                    ? duration(ttft.reduce((a, b) => a + b, 0) / ttft.length)
                    : "Not recorded"}
                </strong>
              </span>
            </div>
            {error && (
              <p className="mt-3 text-sm text-destructive">
                Refresh failed: {error}. Showing last loaded evidence.
              </p>
            )}
            {isActive(run.status) && (
              <p className="mt-3 text-xs text-muted-foreground">
                Stored evidence refreshes every 3 seconds. Live audio monitoring
                awaits RFC-0013 backend stream.
              </p>
            )}
            {!timeline.messages.length && !timeline.spans.length && (
              <p className="mt-3 text-xs text-muted-foreground">
                No finalized transcript or operation evidence stored. Run state
                alone does not prove trace completeness.
              </p>
            )}
            <Tabs
              value={lens}
              onValueChange={(value) => setSearchParams({ lens: value })}
              className="mt-4"
            >
              <TabsList variant="line">
                <TabsTrigger value="waterfall">Waterfall</TabsTrigger>
                <TabsTrigger value="transcript">Transcript</TabsTrigger>
              </TabsList>
            </Tabs>
            <div className="mt-4 grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_19rem]">
              <div className="min-w-0">
                {lens === "waterfall" ? (
                  <Waterfall
                    timeline={timeline}
                    selection={selection}
                    onSelect={select}
                  />
                ) : (
                  <Transcript
                    timeline={timeline}
                    active={isActive(run.status)}
                    onSelect={select}
                  />
                )}
                <Card className="mt-4">
                  <CardHeader>
                    <CardTitle>Recordings</CardTitle>
                    <CardDescription>
                      Full-call tracks. Loaded only after operator action.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col gap-2">
                    {recorded.length ? (
                      recorded.map((artifact) => (
                        <AudioTrack key={artifact.id} artifact={artifact} />
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No recording artifacts registered.
                      </p>
                    )}
                  </CardContent>
                </Card>
                {pipelineLog && <PipelineDebugLog artifact={pipelineLog} />}
              </div>
              <Inspector
                selection={selection}
                timeline={timeline}
                run={run}
                onSelect={select}
              />
            </div>
          </>
        ) : (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>Run evidence unavailable</EmptyTitle>
              <EmptyDescription>Try refreshing this run.</EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </main>
    </div>
  );
}
