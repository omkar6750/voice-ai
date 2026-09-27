import type {
  Exchange,
  Span,
  Timeline,
  Tool,
  ToolContextDelivery,
  ToolResult,
} from "./types";

export const isActive = (status: string) =>
  ["queued", "claimed", "running"].includes(status);

export const stamp = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString() : "Not recorded";

export const clock = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleTimeString() : "Not recorded";

export const duration = (ms: number | null | undefined) =>
  ms == null || !Number.isFinite(ms) || ms < 0
    ? "Not recorded"
    : ms < 1000
      ? Math.round(ms) + " ms"
      : (ms / 1000).toFixed(2) + " s";

export function exchangeSpans(timeline: Timeline, exchange: Exchange): Span[] {
  return timeline.spans.filter((item) => item.exchange_id === exchange.id);
}

export function exchangeTools(timeline: Timeline, exchange: Exchange): Tool[] {
  return timeline.tools.filter((item) => item.exchange_id === exchange.id);
}

export function resultsFor(timeline: Timeline, tool: Tool): ToolResult[] {
  return timeline.tool_results
    .filter((item) => item.tool_invocation_id === tool.id)
    .sort((a, b) => a.sequence - b.sequence);
}

export function deliveryFor(
  timeline: Timeline,
  result: ToolResult,
): ToolContextDelivery | null {
  return (
    timeline.tool_context_deliveries.find(
      (delivery) => delivery.result_id === result.id,
    ) ?? null
  );
}

export function classifierResultsFor(timeline: Timeline, span: Span) {
  return timeline.classifier_results.filter(
    (result) => result.operation_id === span.id,
  );
}

export function classifierDeliveryFor(
  timeline: Timeline,
  result: Timeline["classifier_results"][number],
) {
  return timeline.classifier_context_deliveries.find(
    (delivery) => delivery.classifier_result_id === result.id,
  );
}

export function spanDepth(timeline: Timeline, spanId: string): number {
  let depth = 0;
  const seen = new Set<string>();
  let current = timeline.spans.find((span) => span.id === spanId);
  while (current?.parent_id && !seen.has(current.id)) {
    seen.add(current.id);
    depth += 1;
    current = timeline.spans.find((span) => span.id === current?.parent_id);
  }
  return depth;
}

export function consumingLlm(
  timeline: Timeline,
  result: ToolResult,
): Span | null {
  const delivery = deliveryFor(timeline, result);
  if (delivery?.consuming_span_id) {
    return (
      timeline.spans.find((span) => span.id === delivery.consuming_span_id) ??
      null
    );
  }
  if (!result.consumed_at || !result.consumed_exchange_id) return null;
  return (
    timeline.spans
      .filter(
        (span) =>
          span.exchange_id === result.consumed_exchange_id &&
          span.category.toLowerCase().includes("llm") &&
          Date.parse(span.started_at) >= Date.parse(result.consumed_at!),
      )
      .sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at))[0] ??
    null
  );
}

export function timingWindow(spans: Span[], tools: Tool[]) {
  const starts = [...spans, ...tools]
    .map((item) => Date.parse(item.started_at))
    .filter(Number.isFinite);
  const ends = [...spans, ...tools]
    .map((item) => item.ended_at && Date.parse(item.ended_at))
    .filter((item): item is number => item !== null && Number.isFinite(item));
  if (!starts.length || !ends.length) return null;
  const start = Math.min(...starts);
  const end = Math.max(...ends);
  return { start, end, length: Math.max(1, end - start) };
}
