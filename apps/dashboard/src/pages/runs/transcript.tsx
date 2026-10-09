import { Bot, UserRound, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Marker, MarkerContent } from "@/components/ui/marker";
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageFooter,
  MessageHeader,
} from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import {
  clock,
  duration,
  consumingLlm,
  deliveryFor,
  resultsFor,
  exchangeVisits,
  whatsappReceiptHistory,
  whatsappDeliveryStatus,
} from "./model";
import type { Diagnostic, Selection, Timeline, Tool } from "./types";

function summaryOperationId(diagnostic: Diagnostic): string | null {
  const value = diagnostic.metadata?.summary_operation_id;
  return typeof value === "string" && value ? value : null;
}

function ToolActivity({
  tool,
  timeline,
  onSelect,
}: {
  tool: Tool;
  timeline: Timeline;
  onSelect: (value: Selection) => void;
}) {
  const results = resultsFor(timeline, tool);
  const asyncEvents = timeline.context_events.filter(
    (event) => event.tool_invocation_id === tool.id,
  );
  const composerSpans = timeline.spans.filter(
    (span) =>
      span.category === "composer" &&
      span.attributes?.tool_invocation_id === tool.id,
  );
  return (
    <Message align="start">
      <MessageAvatar>
        <Wrench aria-hidden="true" className="size-4" />
      </MessageAvatar>
      <MessageContent>
        <MessageHeader>
          Agent tool activity · {clock(tool.started_at)}
        </MessageHeader>
        {whatsappDeliveryStatus(timeline, tool) && (
          <p className="text-xs text-muted-foreground">
            {whatsappDeliveryStatus(timeline, tool)}
          </p>
        )}
        {whatsappReceiptHistory(tool).length > 0 && (
          <p className="max-w-full text-left text-xs text-muted-foreground">
            Delivery events: {whatsappReceiptHistory(tool).join(" → ")}
          </p>
        )}
        {asyncEvents.map((event) => (
          <p key={event.id} className="text-left text-xs text-muted-foreground">
            {event.source.replaceAll("_", " ")} ·{" "}
            {event.status.replaceAll("_", " ")}
            {event.delivered_at
              ? " · added to context"
              : " · not added to context"}
            {event.consumed_at
              ? " · consumed by LLM"
              : " · not consumed by LLM"}
            {event.source === "whatsapp_receipt" && event.provider_message_id
              ? ` · ${event.provider_message_id}`
              : ""}
          </p>
        ))}
        {composerSpans.map((span) => (
          <Button
            key={span.id}
            type="button"
            variant="ghost"
            size="sm"
            className="h-auto max-w-full justify-start px-2 text-left text-xs text-primary hover:bg-primary/5 hover:text-primary"
            onClick={() => onSelect({ kind: "span", id: span.id })}
          >
            WhatsApp composer · {span.status.replaceAll("_", " ")} ·{" "}
            {duration(span.duration_ms)}
          </Button>
        ))}
        <Bubble align="start" variant="secondary">
          <BubbleContent asChild>
            <button
              type="button"
              onClick={() => onSelect({ kind: "tool", id: tool.id })}
            >
              Called {tool.binding_key} · {tool.status}
            </button>
          </BubbleContent>
        </Bubble>
        {results.map((result) => {
          const next = consumingLlm(timeline, result);
          const delivery = deliveryFor(timeline, result);
          const exchange = timeline.exchanges.find(
            (item) => item.id === result.consumed_exchange_id,
          );
          return (
            <div
              key={result.id}
              className="flex max-w-full flex-col items-start gap-1"
            >
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onSelect({ kind: "result", id: result.id })}
              >
                Result {result.sequence}
                {result.is_final ? " · final" : " · intermediate"}
              </Button>
              <p className="text-xs text-muted-foreground">
                {delivery?.delivered_at
                  ? "Added to context " + clock(delivery.delivered_at)
                  : "Not recorded as added to context"}
                {delivery?.consumed_at
                  ? " · consumed by LLM " + clock(delivery.consumed_at)
                  : " · not recorded as consumed"}
                {delivery?.consumed_at
                  ? " · exchange " + (exchange?.sequence ?? "?")
                  : ""}
                {next ? " · next recorded LLM: " + next.name : ""}
              </p>
            </div>
          );
        })}
        {!results.length && tool.result !== null && (
          <MessageFooter>Final result stored on tool invocation</MessageFooter>
        )}
        {!results.length && tool.result === null && (
          <MessageFooter>No result recorded</MessageFooter>
        )}
      </MessageContent>
    </Message>
  );
}

export function Transcript({
  timeline,
  active,
  onSelect,
}: {
  timeline: Timeline;
  active: boolean;
  onSelect: (value: Selection) => void;
}) {
  if (!timeline.exchanges.length)
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>No transcript recorded</EmptyTitle>
          <EmptyDescription>
            Finalized speech and tools will appear when evidence is stored.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  return (
    <div className="h-[min(68vh,46rem)] min-h-96 rounded-lg border bg-card">
      <MessageScrollerProvider autoScroll={active}>
        <MessageScroller>
          <MessageScrollerViewport>
            <MessageScrollerContent className="p-4">
              {timeline.exchanges.map((exchange) => {
                const messages = timeline.messages
                  .filter((item) => item.exchange_id === exchange.id)
                  .sort((a, b) => a.sequence - b.sequence);
                const tools = timeline.tools.filter(
                  (item) => item.exchange_id === exchange.id,
                );
                const summaryEvents = timeline.diagnostics.filter(
                  (item) =>
                    item.category === "context_summary" &&
                    item.code !== "consumed" &&
                    item.metadata?.exchange_id === exchange.id,
                );
                const events = [
                  ...messages.map((message) => ({
                    kind: "message" as const,
                    value: message,
                    at: message.source_at ?? message.created_at,
                  })),
                  ...tools.map((tool) => ({
                    kind: "tool" as const,
                    value: tool,
                    at: tool.started_at,
                  })),
                  ...summaryEvents.map((diagnostic) => ({
                    kind: "summary" as const,
                    value: diagnostic,
                    at: diagnostic.occurred_at,
                  })),
                  ...exchangeVisits(timeline, exchange).map((visit) => ({
                    kind: "visit" as const,
                    value: visit,
                    at: visit.entered_at,
                  })),
                ].sort(
                  (a, b) =>
                    Date.parse(a.at) - Date.parse(b.at) ||
                    (a.kind === b.kind ? 0 : a.kind === "tool" ? -1 : 1),
                );
                return (
                  <MessageScrollerItem
                    key={exchange.id}
                    messageId={exchange.id}
                    scrollAnchor={messages.some((item) => item.role === "user")}
                  >
                    <div className="flex flex-col gap-4">
                      <Marker variant="separator">
                        <MarkerContent>
                          {exchange.origin === "opening"
                            ? "Opening"
                            : "Exchange " + exchange.sequence}
                        </MarkerContent>
                      </Marker>
                      {!messages.length && !tools.length && (
                        <p className="text-sm text-muted-foreground">
                          No finalized dialogue or tool call stored.
                        </p>
                      )}
                      {events.map((event) => {
                        if (event.kind === "visit") {
                          return (
                            <Marker key={event.value.id} variant="separator">
                              <MarkerContent>
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() =>
                                    onSelect({
                                      kind: "visit",
                                      id: event.value.id,
                                    })
                                  }
                                >
                                  Entered {event.value.node_key}
                                </Button>
                              </MarkerContent>
                            </Marker>
                          );
                        }
                        if (event.kind === "tool") {
                          return (
                            <ToolActivity
                              key={event.value.id}
                              tool={event.value}
                              timeline={timeline}
                              onSelect={onSelect}
                            />
                          );
                        }
                        if (event.kind === "summary") {
                          const diagnostic = event.value;
                          const operationId = summaryOperationId(diagnostic);
                          const span = timeline.spans.find(
                            (item) => item.id === operationId,
                          );
                          return (
                            <Marker
                              key={diagnostic.diagnostic_id}
                              variant="separator"
                            >
                              <MarkerContent>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  disabled={!span}
                                  aria-label="View context summary details"
                                  onClick={() =>
                                    span &&
                                    onSelect({ kind: "span", id: span.id })
                                  }
                                >
                                  Context summary · {diagnostic.code} ·{" "}
                                  {clock(diagnostic.occurred_at)}
                                  {span
                                    ? ` · ${duration(span.duration_ms)}`
                                    : ""}
                                </Button>
                              </MarkerContent>
                            </Marker>
                          );
                        }
                        const message = event.value;
                        const agent = ["assistant", "agent"].includes(
                          message.role,
                        );
                        return (
                          <Message
                            key={message.id}
                            align={agent ? "start" : "end"}
                          >
                            <MessageAvatar>
                              {agent ? (
                                <Bot aria-hidden="true" className="size-4" />
                              ) : (
                                <UserRound
                                  aria-hidden="true"
                                  className="size-4"
                                />
                              )}
                            </MessageAvatar>
                            <MessageContent>
                              <MessageHeader>
                                {agent ? "Agent" : "Caller"} ·{" "}
                                {clock(message.source_at ?? message.created_at)}
                              </MessageHeader>
                              <Bubble
                                align={agent ? "start" : "end"}
                                variant={agent ? "default" : "outline"}
                              >
                                <BubbleContent asChild>
                                  <button
                                    type="button"
                                    className="whitespace-pre-wrap"
                                    onClick={() =>
                                      onSelect({
                                        kind: "message",
                                        id: message.id,
                                      })
                                    }
                                  >
                                    {message.content}
                                  </button>
                                </BubbleContent>
                              </Bubble>
                              {message.interrupted && (
                                <MessageFooter>
                                  Interrupted · spoken audio may be shorter than
                                  generated text
                                </MessageFooter>
                              )}
                            </MessageContent>
                          </Message>
                        );
                      })}
                    </div>
                  </MessageScrollerItem>
                );
              })}
            </MessageScrollerContent>
          </MessageScrollerViewport>
          <MessageScrollerButton />
        </MessageScroller>
      </MessageScrollerProvider>
    </div>
  );
}
