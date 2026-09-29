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

export function whatsappDeliveryStatus(
  timeline: Timeline,
  tool: Tool,
): string | null {
  if (
    !tool.binding_key.startsWith("whatsapp_") &&
    !tool.provider_message_id &&
    !tool.receipts.length
  )
    return null;
  const receipts = [...tool.receipts].sort(
    (left, right) => Number(right.timestamp ?? 0) - Number(left.timestamp ?? 0),
  );
  const latest = receipts[0];
  const asyncSend = timeline.context_events.find((event) => {
    if (event.tool_invocation_id !== tool.id || event.source !== "tool_result")
      return false;
    const payload = event.payload;
    if (!payload || typeof payload !== "object" || Array.isArray(payload))
      return false;
    const result = (payload as Record<string, unknown>).result;
    return !!result && typeof result === "object" && !Array.isArray(result)
      && (result as Record<string, unknown>).status === "accepted";
  });
  if (!latest) {
    if (asyncSend)
      return isActive(timeline.run.status)
        ? "Meta accepted the message · waiting for delivery webhook"
        : "Meta accepted the message · delivery status unconfirmed (no webhook receipt)";
    if (!tool.provider_message_id || tool.provider_message_id === "unknown") {
      const result =
        tool.result &&
        typeof tool.result === "object" &&
        !Array.isArray(tool.result)
          ? (tool.result as Record<string, unknown>)
          : null;
      if (tool.status === "failed" || result?.status === "error") {
        const error = typeof result?.error === "string" ? result.error : null;
        return `WhatsApp send failed${error ? ` · ${error}` : ""}`;
      }
      if (["pending", "queued", "running"].includes(tool.status))
        return "WhatsApp send in progress · waiting for Meta response";
      if (result?.status === "ok")
        return "Meta response received without a message ID · delivery status unavailable";
      return "WhatsApp send/delivery status unavailable · no provider message ID recorded";
    }
    return isActive(timeline.run.status)
      ? "Meta accepted the message · waiting for delivery webhook"
      : "Meta accepted the message · delivery status unavailable (no webhook receipt received)";
  }
  if (latest.status === "failed") {
    const details = (latest.errors ?? [])
      .map((error) => {
        if (!error || typeof error !== "object" || Array.isArray(error))
          return null;
        const item = error as Record<string, unknown>;
        return [item.title, item.message]
          .filter((value): value is string => typeof value === "string")
          .join(": ");
      })
      .filter(Boolean)
      .join("; ");
    return `WhatsApp delivery failed${details ? ` · ${details}` : ""}`;
  }
  if (latest.status === "read") return "WhatsApp message read";
  if (latest.status === "delivered") return "WhatsApp message delivered";
  if (latest.status === "sent")
    return "WhatsApp message sent · recipient delivery not confirmed";
  return `WhatsApp status: ${latest.status}`;
}

export function whatsappReceiptHistory(tool: Tool): string[] {
  return [...tool.receipts]
    .sort(
      (left, right) =>
        Number(left.timestamp ?? 0) - Number(right.timestamp ?? 0),
    )
    .map((receipt) => {
      const timestamp = Number(receipt.timestamp);
      const time = Number.isFinite(timestamp)
        ? new Date(timestamp * 1000).toLocaleTimeString()
        : "time unavailable";
      const errors = (receipt.errors ?? [])
        .map((error) => {
          if (!error || typeof error !== "object" || Array.isArray(error))
            return null;
          const item = error as Record<string, unknown>;
          return [item.title, item.message]
            .filter((value): value is string => typeof value === "string")
            .join(": ");
        })
        .filter(Boolean)
        .join("; ");
      return `${receipt.status} · ${time}${errors ? ` · ${errors}` : ""}`;
    });
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
