import type { Exchange, Span, Timeline, Tool, ToolResult } from "./types";

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

export function consumingLlm(
  timeline: Timeline,
  result: ToolResult,
): Span | null {
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
