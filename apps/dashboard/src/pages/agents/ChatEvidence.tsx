import { Bot, UserRound, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageHeader,
  MessageFooter,
} from "@/components/ui/message";
import { Marker, MarkerContent } from "@/components/ui/marker";
import { Json, Value } from "../runs/inspector";

type Payload = Record<string, unknown>;
export type ChatEntry = {
  id: string;
  run_id: string;
  sequence: number;
  kind: string;
  payload: Payload;
  saved?: boolean;
};
const human = (value: unknown) => String(value ?? "").replaceAll("_", " ");
export function transcriptEntries(entries: ChatEntry[]) {
  return entries.filter((entry) => {
    const p = entry.payload;
    if (entry.kind !== "evidence") return true;
    if (p.kind === "operation_started")
      return !entries.some(
        (other) =>
          other.payload.kind === "span" &&
          other.payload.operation_id === p.operation_id,
      );
    if (p.kind === "tool_started" || p.kind === "tool_result")
      return !entries.some(
        (other) =>
          other.payload.kind === "tool_ended" &&
          other.payload.invocation_id === p.invocation_id,
      );
    return true;
  });
}
function eventTitle(p: Payload) {
  switch (p.kind) {
    case "flow_visit_started":
      return `Entered ${p.node_key}`;
    case "interruption":
      return "Response interrupted";
    case "classifier_result":
      return `Automatic classifier (${human(p.phase ?? "configured trigger")}) - ${human(p.status ?? "decision recorded")}`;
    case "classifier_context_updated":
      return "Classifier result added to context";
    case "tool_result_context_updated":
      return "Tool result added to context";
    case "tool_result_consumed":
      return "Tool result used by LLM";
    case "classifier_result_consumed":
      return "Classifier result used by LLM";
    case "flow_visit_ended":
      return `Left node - ${human(p.status)}`;
    case "diagnostic":
      return String(p.message ?? human(p.code));
    case "operation_started":
      if (p.category === "classifier") return `Automatic classifier - running`;
      if (p.category === "composer") return "WhatsApp composer · writing message";
      return `${human(p.category ?? p.name)} - running`;
    case "span":
      if (p.category === "classifier")
        return `Automatic classifier - ${human(p.status)}${typeof p.duration_ms === "number" ? ` - ${Math.round(p.duration_ms)} ms` : ""}`;
      if (p.category === "composer")
        return `WhatsApp composer · ${human(p.status)}${typeof p.duration_ms === "number" ? ` · ${Math.round(p.duration_ms)} ms` : ""}`;
      return `${human(p.category ?? p.name)} - ${human(p.status)}${typeof p.duration_ms === "number" ? ` - ${Math.round(p.duration_ms)} ms` : ""}`;
    default:
      return human(p.kind ?? "Context update");
  }
}
export function ChatTranscriptEntry({
  entry,
  entries,
  inspect,
}: {
  entry: ChatEntry;
  entries: ChatEntry[];
  inspect: (entry: ChatEntry) => void;
}) {
  const p = entry.payload;
  const tool =
    entry.kind === "evidence" &&
    ["tool_started", "tool_result", "tool_ended"].includes(String(p.kind));
  const start = tool
    ? entries.find(
        (other) =>
          other.payload.kind === "tool_started" &&
          other.payload.invocation_id === p.invocation_id,
      )?.payload
    : null;
  const name = p.binding_key ?? start?.binding_key ?? "tool";
  const duration =
    tool &&
    typeof p.ended_ns === "number" &&
    typeof start?.started_ns === "number"
      ? Math.round((p.ended_ns - start.started_ns) / 1e6)
      : null;
  if (entry.kind === "evidence" && !tool)
    return (
      <Marker variant="separator">
        <MarkerContent>
          <Button size="sm" variant="ghost" className={p.category === "composer" ? "text-primary hover:bg-primary/5 hover:text-primary" : undefined} onClick={() => inspect(entry)}>
            {eventTitle(p)}
          </Button>
        </MarkerContent>
      </Marker>
    );
  const agent = entry.kind === "assistant" || tool;
  const text = tool
    ? `Called ${name} - ${human(p.status ?? (p.kind === "tool_result" ? "result received" : "running"))}`
    : entry.kind === "error"
      ? String(p.message ?? "Execution failed")
      : String(p.text ?? "") ||
        (p.status === "streaming"
          ? "Generating..."
          : human(p.status ?? "No text output"));
  return (
    <Message align={entry.kind === "user" ? "end" : "start"}>
      <MessageAvatar>
        {tool ? (
          <Wrench className="size-4" />
        ) : agent ? (
          <Bot className="size-4" />
        ) : (
          <UserRound className="size-4" />
        )}
      </MessageAvatar>
      <MessageContent>
        <MessageHeader>
          {tool
            ? name === "classify_lead"
              ? "Agent called classifier tool"
              : "Agent tool activity"
            : agent
              ? "Agent"
              : entry.kind === "error"
                ? "Error"
                : "You"}
        </MessageHeader>
        <Bubble
          align={entry.kind === "user" ? "end" : "start"}
          variant={
            entry.kind === "error"
              ? "destructive"
              : agent
                ? "secondary"
                : "default"
          }
        >
          <BubbleContent asChild>
            <button
              type="button"
              className="w-full whitespace-pre-wrap text-left outline-offset-4"
              aria-label={`Inspect ${tool ? name : entry.kind} details`}
              onClick={() => inspect(entry)}
            >
              {text}
            </button>
          </BubbleContent>
        </Bubble>
        <MessageFooter>
          {human(p.status ?? (tool ? "running" : entry.kind))}
          {duration !== null ? ` - ${duration} ms` : ""} -{" "}
          {entry.saved ? "Saved" : "Saving..."}
          {entry.kind === "error" && p.diagnostic_id
            ? ` - ${p.diagnostic_id}`
            : ""}
        </MessageFooter>
      </MessageContent>
    </Message>
  );
}
export function ChatInspection({ value }: { value: unknown }) {
  const data = value as {
    message: Payload;
    tool?: Payload;
    evidence?: Record<string, Payload[]>;
    operations?: Payload[];
  };
  const tool = data.tool;
  const results = tool
    ? (data.evidence?.tool_results?.filter(
        (r) => r.tool_invocation_id === tool.id,
      ) ?? [])
    : [];
  const deliveries = tool
    ? (data.evidence?.tool_context_deliveries?.filter(
        (r) => r.tool_invocation_id === tool.id,
      ) ?? [])
    : [];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      {tool && (
        <section>
          <h4 className="text-sm font-medium">
            Called {String(tool.binding_key)}
          </h4>
          <dl>
            <Value label="Status">{human(tool.status)}</Value>
            <Value label="Duration">
              {tool.started_at && tool.ended_at
                ? `${Math.round(Date.parse(String(tool.ended_at)) - Date.parse(String(tool.started_at)))} ms`
                : "Not recorded"}
            </Value>
          </dl>
          <Json label="Tool arguments" value={tool.arguments} />
          <Json label="Tool result" value={tool.result} />
          <Json label="Result history" value={results} />
          <Json label="Context delivery" value={deliveries} />
        </section>
      )}
      {data.operations?.map((op) => {
        const composerInput = op.category === "composer" && op.input_payload && typeof op.input_payload === "object" && !Array.isArray(op.input_payload)
          ? op.input_payload as Payload : null;
        const composerDiagnostics = op.category === "composer"
          ? data.evidence?.diagnostics?.filter((item) => (item.metadata as Payload | undefined)?.operation_id === op.id) ?? []
          : [];
        return <section key={String(op.id)} className="flex flex-col gap-2">
          <h4 className="text-sm font-medium">
            {op.category === "composer" ? "WhatsApp composer" : `${human(op.category)} - ${human(op.name)}`}
          </h4>
          <dl>
            <Value label="Provider">
              {String(op.provider ?? "Not applicable")}
            </Value>
            <Value label="Model">{String(op.model ?? "Not applicable")}</Value>
            <Value label="Status">{human(op.status)}</Value>
            <Value label="Duration">
              {op.duration_ms == null ? "Not recorded" : `${op.duration_ms} ms`}
            </Value>
            {op.category !== "flow_node" && (
              <>
                <Value label="Input tokens">
                  {String(op.prompt_tokens ?? "Not reported")}
                </Value>
                <Value label="Output tokens">
                  {String(op.completion_tokens ?? "Not reported")}
                </Value>
                <Value label="Total tokens">
                  {String(op.total_tokens ?? "Not reported")}
                </Value>
              </>
            )}
          </dl>
          {op.category === "composer" ? (
            <>
              <Json label="Composer system prompt" value={composerInput?.system_prompt} />
              <Json label="Plain Caller/Agent transcript" value={composerInput?.transcript} />
              <Json label="Template fields and required links" value={{ fields: composerInput?.template_fields, required_urls: composerInput?.required_urls }} />
              <Json label="Composed template fields" value={op.output_payload} />
              <p className="text-xs text-muted-foreground">The WhatsApp tool result records whether Meta accepted the send. Composition alone does not mean a message was sent.</p>
              {composerDiagnostics.map((item) => <p key={String(item.diagnostic_id)} className="border-l-2 border-destructive pl-3 text-xs"><span className="font-medium">{String(item.message)}</span><br />Diagnostic ID: {String(item.diagnostic_id)}</p>)}
            </>
          ) : (
            <>
              {op.input_payload != null && <Json label="Input context and tool definitions" value={op.input_payload} />}
              {op.output_payload != null && <Json label="Output and LLM tool calls" value={op.output_payload} />}
            </>
          )}
          {op.category === "flow_node" && (
            <p className="text-xs text-muted-foreground">
              This duration is time spent in the node, including waiting for the
              caller. It is not an LLM request. A failed visit means execution
              stopped while this node was active.
            </p>
          )}
        </section>;
      })}
      <Json label="Selected event" value={data.message} />
      {!tool && data.evidence && (
        <Json
          label="Routing, classifier and context evidence"
          value={data.evidence}
        />
      )}
    </div>
  );
}
