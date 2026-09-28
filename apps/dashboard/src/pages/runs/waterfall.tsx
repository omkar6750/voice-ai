import { Fragment } from "react";
import { ChevronDown, GitBranch, Wrench, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Marker, MarkerContent } from "@/components/ui/marker";
import { cn } from "@/lib/utils";
import {
  classifierDeliveryFor,
  classifierResultsFor,
  duration,
  deliveryFor,
  exchangeSpans,
  exchangeTools,
  resultsFor,
  spanDepth,
  timingWindow,
  whatsappReceiptHistory,
  whatsappDeliveryStatus,
} from "./model";
import type { Selection, Span, Timeline, Tool } from "./types";

type Operation =
  | {
      kind: "span";
      item: Span;
      start: string;
      end: string | null;
      label: string;
      depth: number;
    }
  | {
      kind: "tool";
      item: Tool;
      start: string;
      end: string | null;
      label: string;
      depth: number;
    };

function Bar({
  start,
  end,
  window,
  kind,
}: {
  start: string;
  end: string | null;
  window: { start: number; length: number } | null;
  kind: "span" | "tool";
}) {
  if (!window || !end)
    return (
      <span className="text-xs text-muted-foreground">Timing incomplete</span>
    );
  const from = Date.parse(start);
  const to = Date.parse(end);
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return null;
  const x = Math.max(
    0,
    Math.min(999, ((from - window.start) / window.length) * 1000),
  );
  const width = Math.max(
    3,
    Math.min(1000 - x, ((to - from) / window.length) * 1000),
  );
  return (
    <svg
      viewBox="0 0 1000 16"
      preserveAspectRatio="none"
      className="h-4 w-full rounded bg-muted/50"
      role="img"
      aria-label={kind + " timing bar"}
    >
      <rect
        x={x}
        y="2"
        width={width}
        height="12"
        rx="3"
        className={kind === "tool" ? "fill-accent-foreground" : "fill-primary"}
      />
    </svg>
  );
}

export function Waterfall({
  timeline,
  selection,
  onSelect,
}: {
  timeline: Timeline;
  selection: Selection;
  onSelect: (selection: Selection) => void;
}) {
  if (!timeline.exchanges.length)
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>No exchanges recorded</EmptyTitle>
          <EmptyDescription>
            Run exists, but turn evidence has not arrived.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  return (
    <div className="flex flex-col gap-3">
      {timeline.exchanges.map((exchange, index) => {
        const spans = exchangeSpans(timeline, exchange);
        const tools = exchangeTools(timeline, exchange);
        const visits = timeline.flow_visits.filter((visit) =>
          spans.some((span) => span.id === visit.span_id),
        );
        const ops: Operation[] = [
          ...spans.map((item) => ({
            kind: "span" as const,
            item,
            start: item.started_at,
            end: item.ended_at,
            label: item.name,
            depth: spanDepth(timeline, item.id),
          })),
          ...tools.map((item) => ({
            kind: "tool" as const,
            item,
            start: item.started_at,
            end: item.ended_at,
            label: item.binding_key,
            depth: item.llm_operation_id
              ? spanDepth(timeline, item.llm_operation_id) + 1
              : 0,
          })),
        ].sort((a, b) => Date.parse(a.start) - Date.parse(b.start));
        const window = timingWindow(spans, tools);
        const opening = ["opening", "greeting"].includes(exchange.origin);
        const speech = timeline.messages.find(
          (item) => item.exchange_id === exchange.id && item.role === "user",
        );
        return (
          <Collapsible
            key={exchange.id}
            defaultOpen={index === 0}
            className="rounded-lg border bg-card"
          >
            <CollapsibleTrigger asChild>
              <Button
                variant="ghost"
                className="h-auto w-full justify-between gap-3 px-4 py-3 text-left"
              >
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">
                    {opening ? "Opening" : "Exchange " + exchange.sequence}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {speech?.content ?? exchange.origin.replaceAll("_", " ")}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  {window ? duration(window.length) : "No complete timing"}
                </span>
                <ChevronDown data-icon="inline-end" aria-hidden="true" />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="border-t px-3 py-2">
              {timeline.interruptions
                .filter((item) => item.exchange_id === exchange.id)
                .map((interruption) => (
                  <Button
                    key={interruption.id}
                    variant="ghost"
                    size="sm"
                    className="mb-1 w-full justify-start gap-2 border border-destructive/40 text-left text-xs text-destructive"
                    onClick={() =>
                      onSelect({ kind: "interruption", id: interruption.id })
                    }
                  >
                    <Zap data-icon="inline-start" />
                    Barge-in · {interruption.reason} · interrupted{" "}
                    {interruption.interrupted_operation_ids.length} operations
                    {interruption.interrupted_tool_invocation_ids.length
                      ? ` · ${interruption.interrupted_tool_invocation_ids.length} tools`
                      : ""}
                  </Button>
                ))}
              {visits.map((visit) => (
                <Button
                  key={visit.id}
                  variant="ghost"
                  size="sm"
                  className="w-full justify-start"
                  onClick={() => onSelect({ kind: "visit", id: visit.id })}
                >
                  <GitBranch data-icon="inline-start" /> Node {visit.node_key}
                </Button>
              ))}
              {ops.length ? (
                ops.map((op) => {
                  const chosen =
                    selection.kind === op.kind && selection.id === op.item.id;
                  const ms = op.end
                    ? Date.parse(op.end) - Date.parse(op.start)
                    : null;
                  return (
                    <Fragment key={op.kind + op.item.id}>
                      <Button
                        variant="ghost"
                        className={cn(
                          "h-auto w-full justify-start gap-3 px-2 py-2 text-left",
                          chosen && "bg-accent",
                          op.depth === 1 && "pl-6",
                          op.depth >= 2 && "pl-10",
                        )}
                        onClick={() =>
                          onSelect({ kind: op.kind, id: op.item.id })
                        }
                      >
                        {op.kind === "tool" ? (
                          <Wrench data-icon="inline-start" />
                        ) : (
                          <Zap data-icon="inline-start" />
                        )}
                        <span className="w-28 shrink-0 truncate text-xs font-medium">
                          {op.kind === "tool" ? "Tool" : op.item.category}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-xs">
                          {op.label}
                        </span>
                        <span className="w-20 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                          {duration(ms)}
                        </span>
                      </Button>
                      <div className="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-2 px-2 pb-2">
                        <span className="text-xs text-muted-foreground">
                          {op.kind === "span"
                            ? (op.item.provider ?? "Runtime")
                            : op.item.status}
                        </span>
                        <Bar
                          start={op.start}
                          end={op.end}
                          window={window}
                          kind={op.kind}
                        />
                      </div>
                      {op.kind === "tool" &&
                        whatsappDeliveryStatus(timeline, op.item) && (
                          <div className="pl-9 pb-2 text-xs text-muted-foreground">
                            <p>{whatsappDeliveryStatus(timeline, op.item)}</p>
                            {whatsappReceiptHistory(op.item).length > 0 && (
                              <p>
                                Delivery events:{" "}
                                {whatsappReceiptHistory(op.item).join(" → ")}
                              </p>
                            )}
                          </div>
                        )}
                      {op.kind === "span" &&
                        op.item.category === "classifier" &&
                        classifierResultsFor(timeline, op.item).map(
                          (result) => {
                            const delivery = classifierDeliveryFor(
                              timeline,
                              result,
                            );
                            return (
                              <div
                                key={result.id}
                                className="pl-9 text-xs text-muted-foreground"
                              >
                                Classifier {result.phase} · {result.status} ·
                                context {delivery?.status ?? "not recorded"}
                                {delivery?.consuming_operation_id
                                  ? ` · consumed by ${delivery.consuming_operation_id}`
                                  : ""}
                              </div>
                            );
                          },
                        )}
                      {op.kind === "tool" &&
                        resultsFor(timeline, op.item).map((result) => (
                          <Button
                            key={result.id}
                            variant="ghost"
                            size="sm"
                            className="w-full justify-start pl-9 text-xs"
                            onClick={() =>
                              onSelect({ kind: "result", id: result.id })
                            }
                          >
                            Result {result.sequence}
                            {result.is_final ? " · final" : " · intermediate"}
                            {deliveryFor(timeline, result) ? (
                              <span className="ml-auto text-muted-foreground">
                                {deliveryFor(timeline, result)?.status ===
                                "consumed"
                                  ? `Consumed by LLM${
                                      deliveryFor(timeline, result)
                                        ?.consuming_span_id
                                        ? ` · ${deliveryFor(timeline, result)?.consuming_span_id}`
                                        : ""
                                    }`
                                  : `Context ${deliveryFor(timeline, result)?.status}`}
                                {deliveryFor(timeline, result)
                                  ?.context_message_index != null
                                  ? ` · message ${deliveryFor(timeline, result)?.context_message_index}`
                                  : ""}
                              </span>
                            ) : result.consumed_exchange_id ? (
                              <span className="ml-auto text-muted-foreground">
                                Consumed in exchange{" "}
                                {timeline.exchanges.find(
                                  (item) =>
                                    item.id === result.consumed_exchange_id,
                                )?.sequence ?? "?"}
                              </span>
                            ) : null}
                          </Button>
                        ))}
                    </Fragment>
                  );
                })
              ) : (
                <Marker>
                  <MarkerContent>
                    No timed operations recorded for this exchange.
                  </MarkerContent>
                </Marker>
              )}
            </CollapsibleContent>
          </Collapsible>
        );
      })}
      {timeline.spans.some((span) => !span.exchange_id) ||
      timeline.tools.some((tool) => !tool.exchange_id) ? (
        <div className="rounded-lg border bg-card p-3">
          <p className="mb-2 text-sm font-medium">Outside exchange</p>
          {[
            ...timeline.spans
              .filter((span) => !span.exchange_id)
              .map((span) => ({
                kind: "span" as const,
                id: span.id,
                label: span.name,
              })),
            ...timeline.tools
              .filter((tool) => !tool.exchange_id)
              .map((tool) => ({
                kind: "tool" as const,
                id: tool.id,
                label: tool.binding_key,
              })),
          ].map((item) => (
            <Button
              key={item.id}
              variant="ghost"
              className="w-full justify-start"
              onClick={() => onSelect({ kind: item.kind, id: item.id })}
            >
              {item.label}
              {item.kind === "tool" &&
                (() => {
                  const tool = timeline.tools.find(
                    (entry) => entry.id === item.id,
                  );
                  const status = tool && whatsappDeliveryStatus(timeline, tool);
                  return status ? ` · ${status}` : "";
                })()}
            </Button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
