import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { clock, consumingLlm, duration, resultsFor, stamp } from "./model";
import type { RunDetail, Selection, Timeline } from "./types";

function Value({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-2 border-b py-2 text-xs last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all">{children}</dd>
    </div>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="flex min-w-0 flex-col gap-1">
      <h4 className="text-xs font-medium">{label}</h4>
      <pre className="max-h-72 overflow-auto rounded-md bg-muted p-2 font-mono text-xs whitespace-pre-wrap break-all">
        {value === undefined ? "Not recorded" : JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

function Evidence({
  selection,
  timeline,
  run,
  onSelect,
}: {
  selection: Selection;
  timeline: Timeline;
  run: RunDetail;
  onSelect: (selection: Selection) => void;
}) {
  const config = run.resolved_config;
  if (selection.kind === "run")
    return (
      <>
        <CardHeader>
          <CardTitle>Run details</CardTitle>
          <CardDescription>Stored execution snapshot</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <dl>
            <Value label="Run">{run.id}</Value>
            <Value label="Channel">{run.channel}</Value>
            <Value label="State">{run.status}</Value>
            <Value label="Started">{stamp(run.started_at)}</Value>
            <Value label="Ended">{stamp(run.ended_at)}</Value>
            <Value label="Call">
              {timeline.call?.id ?? "Browser / not linked"}
            </Value>
            <Value label="Hash">{run.config_hash ?? "Not recorded"}</Value>
          </dl>
          {run.error && <Json label="Run error" value={run.error} />}
          <Button
            variant="outline"
            onClick={() => onSelect({ kind: "prompt" })}
          >
            System prompt
          </Button>
          <Button asChild variant="link">
            <Link
              to={
                "/agents/" +
                timeline.run.agent_id +
                "/versions/" +
                timeline.run.agent_version_id
              }
            >
              Pinned agent version
            </Link>
          </Button>
          <p className="text-xs text-muted-foreground">
            Prompts and settings are from this run's resolved snapshot. Mutable
            external data is not replayed.
          </p>
        </CardContent>
      </>
    );
  if (selection.kind === "prompt") {
    const flow = config?.flow as
      | {
          prompt_composition?: string;
          nodes?: { id: string; prompt: string }[];
        }
      | undefined;
    return (
      <>
        <CardHeader>
          <CardTitle>System prompt</CardTitle>
          <CardDescription>Resolved at call start</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Json
            label="Global instruction"
            value={config?.system_prompt ?? "Not recorded"}
          />
          <Value label="Composition">
            {flow?.prompt_composition ?? "Not recorded"}
          </Value>
          {flow?.nodes?.map((node) => (
            <Json
              key={node.id}
              label={"Node · " + node.id}
              value={node.prompt}
            />
          ))}
          <p className="text-xs text-muted-foreground">
            Exact LLM request context, when captured, appears on each LLM span.
          </p>
        </CardContent>
      </>
    );
  }
  if (selection.kind === "message") {
    const message = timeline.messages.find((item) => item.id === selection.id);
    if (!message) return null;
    const exchange = timeline.exchanges.find(
      (item) => item.id === message.exchange_id,
    );
    const spans = timeline.spans.filter(
      (item) => item.exchange_id === message.exchange_id,
    );
    const tools = timeline.tools.filter(
      (item) => item.exchange_id === message.exchange_id,
    );
    return (
      <>
        <CardHeader>
          <CardTitle>
            {["assistant", "agent"].includes(message.role)
              ? "Agent message"
              : "Caller message"}
          </CardTitle>
          <CardDescription>Finalized transcript evidence</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <dl>
            <Value label="Exchange">{exchange?.sequence ?? "Unknown"}</Value>
            <Value label="Source">{stamp(message.source_at)}</Value>
            <Value label="Stored">{stamp(message.created_at)}</Value>
            <Value label="Playback">
              {stamp(message.playback_started_at)} →{" "}
              {stamp(message.playback_ended_at)}
            </Value>
            <Value label="Interrupted">
              {message.interrupted ? "Yes" : "No"}
            </Value>
          </dl>
          <Json label="Finalized text" value={message.content} />
          <p className="text-xs text-muted-foreground">
            Related operations share this exchange; exact message-to-operation
            links are not stored.
          </p>
          {spans.map((span) => (
            <Button
              key={span.id}
              variant="ghost"
              size="sm"
              className="justify-start"
              onClick={() => onSelect({ kind: "span", id: span.id })}
            >
              {span.category} · {span.name}
            </Button>
          ))}
          {tools.map((tool) => (
            <Button
              key={tool.id}
              variant="ghost"
              size="sm"
              className="justify-start"
              onClick={() => onSelect({ kind: "tool", id: tool.id })}
            >
              Tool · {tool.binding_key}
            </Button>
          ))}
        </CardContent>
      </>
    );
  }
  if (selection.kind === "span") {
    const span = timeline.spans.find((item) => item.id === selection.id);
    if (!span) return null;
    return (
      <>
        <CardHeader>
          <CardTitle>{span.name}</CardTitle>
          <CardDescription>
            {span.category} · {span.status}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <dl>
            <Value label="Provider">{span.provider ?? "Runtime"}</Value>
            <Value label="Model">{span.model ?? "Not recorded"}</Value>
            <Value label="Started">{stamp(span.started_at)}</Value>
            <Value label="Ended">{stamp(span.ended_at)}</Value>
            <Value label="Duration">{duration(span.duration_ms)}</Value>
            <Value label="First token">{duration(span.ttfb_ms)}</Value>
            <Value label="First audio">{duration(span.ttfa_ms)}</Value>
            <Value label="Input tokens">
              {span.prompt_tokens ?? "Not recorded"}
            </Value>
            <Value label="Output tokens">
              {span.completion_tokens ?? "Not recorded"}
            </Value>
            <Value label="Reasoning tokens">
              {span.reasoning_tokens ?? "Not recorded"}
            </Value>
            <Value label="OTel trace">
              {span.otel_trace_id ?? "Not recorded"}
            </Value>
            <Value label="OTel span">
              {span.otel_span_id ?? "Not recorded"}
            </Value>
          </dl>
          <Json label="Provider input / prompt" value={span.input} />
          <Json
            label="Provider output / reasoning if captured"
            value={span.output}
          />
          <Json label="Attributes" value={span.attributes} />
          {timeline.tools
            .filter((item) => item.llm_operation_id === span.id)
            .map((tool) => (
              <Button
                key={tool.id}
                variant="outline"
                size="sm"
                onClick={() => onSelect({ kind: "tool", id: tool.id })}
              >
                Called {tool.binding_key}
              </Button>
            ))}
        </CardContent>
      </>
    );
  }
  if (selection.kind === "tool") {
    const tool = timeline.tools.find((item) => item.id === selection.id);
    if (!tool) return null;
    return (
      <>
        <CardHeader>
          <CardTitle>{tool.binding_key}</CardTitle>
          <CardDescription>Tool invocation · {tool.status}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <dl>
            <Value label="Started">{stamp(tool.started_at)}</Value>
            <Value label="Ended">{stamp(tool.ended_at)}</Value>
            <Value label="Duration">
              {tool.ended_at
                ? duration(
                    Date.parse(tool.ended_at) - Date.parse(tool.started_at),
                  )
                : "Not recorded"}
            </Value>
            <Value label="Call ID">
              {tool.function_call_id ?? "Not recorded"}
            </Value>
            <Value label="Provider msg">
              {tool.provider_message_id ?? "Not recorded"}
            </Value>
          </dl>
          {tool.llm_operation_id && (
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                onSelect({ kind: "span", id: tool.llm_operation_id! })
              }
            >
              Originating LLM operation
            </Button>
          )}
          <Json label="Arguments" value={tool.arguments} />
          <Json label="Final result" value={tool.result} />
          {resultsFor(timeline, tool).map((result) => (
            <Button
              key={result.id}
              variant="ghost"
              size="sm"
              onClick={() => onSelect({ kind: "result", id: result.id })}
            >
              Result {result.sequence}
              {result.is_final ? " · final" : ""}
            </Button>
          ))}
        </CardContent>
      </>
    );
  }
  if (selection.kind === "result") {
    const result = timeline.tool_results.find(
      (item) => item.id === selection.id,
    );
    if (!result) return null;
    const next = consumingLlm(timeline, result);
    return (
      <>
        <CardHeader>
          <CardTitle>Tool result {result.sequence}</CardTitle>
          <CardDescription>
            {result.is_final ? "Final" : "Intermediate"} result
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <dl>
            <Value label="Occurred">{stamp(result.occurred_at)}</Value>
            <Value label="Consumed">{stamp(result.consumed_at)}</Value>
            <Value label="Exchange">
              {timeline.exchanges.find(
                (item) => item.id === result.consumed_exchange_id,
              )?.sequence ?? "Not recorded"}
            </Value>
          </dl>
          <Json label="Result supplied to context" value={result.payload} />
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              onSelect({ kind: "tool", id: result.tool_invocation_id })
            }
          >
            Originating tool
          </Button>
          {next && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => onSelect({ kind: "span", id: next.id })}
              >
                First later LLM request · {clock(next.started_at)}
              </Button>
              <p className="text-xs text-muted-foreground">
                Linked by exchange and timestamp, not an explicit
                consuming-operation ID.
              </p>
            </>
          )}
        </CardContent>
      </>
    );
  }
  const visit = timeline.flow_visits.find((item) => item.id === selection.id);
  if (!visit) return null;
  return (
    <>
      <CardHeader>
        <CardTitle>Flow node · {visit.node_key}</CardTitle>
        <CardDescription>Visit {visit.sequence}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl>
          <Value label="Entered">{stamp(visit.entered_at)}</Value>
          <Value label="Exited">{stamp(visit.exited_at)}</Value>
        </dl>
        <Button
          variant="outline"
          size="sm"
          onClick={() => onSelect({ kind: "span", id: visit.span_id })}
        >
          Timing span
        </Button>
        {visit.triggered_by_tool_id && (
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              onSelect({ kind: "tool", id: visit.triggered_by_tool_id! })
            }
          >
            Triggering tool
          </Button>
        )}
      </CardContent>
    </>
  );
}

export function Inspector({
  selection,
  timeline,
  run,
  onSelect,
  mobileOpen,
  onMobileOpenChange,
}: {
  selection: Selection;
  timeline: Timeline;
  run: RunDetail;
  onSelect: (selection: Selection) => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
}) {
  const body = (
    <Evidence
      selection={selection}
      timeline={timeline}
      run={run}
      onSelect={onSelect}
    />
  );
  return (
    <>
      <Card className="hidden h-fit min-w-0 xl:sticky xl:top-4 xl:block">
        {body}
      </Card>
      <Sheet open={mobileOpen} onOpenChange={onMobileOpenChange}>
        <SheetContent className="overflow-y-auto xl:hidden">
          <SheetHeader>
            <SheetTitle>Evidence details</SheetTitle>
            <SheetDescription>
              Run, prompt, message, provider, and tool data.
            </SheetDescription>
          </SheetHeader>
          <div className="min-w-0">{body}</div>
        </SheetContent>
      </Sheet>
    </>
  );
}
