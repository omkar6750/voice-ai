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
  consumingLlm,
  deliveryFor,
  resultsFor,
  whatsappReceiptHistory,
  whatsappDeliveryStatus,
} from "./model";
import type { Selection, Timeline, Tool } from "./types";

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
  return (
    <Message align="end">
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
          <p className="max-w-full text-right text-xs text-muted-foreground">
            Delivery events: {whatsappReceiptHistory(tool).join(" → ")}
          </p>
        )}
        {asyncEvents.map((event) => (
          <p key={event.id} className="text-right text-xs text-muted-foreground">
            {event.source.replaceAll("_", " ")} · {event.status.replaceAll("_", " ")}
            {event.delivered_at ? " · added to context" : " · not added to context"}
            {event.consumed_at ? " · consumed by LLM" : " · not consumed by LLM"}
            {event.source === "whatsapp_receipt" && event.provider_message_id
              ? ` · ${event.provider_message_id}`
              : ""}
          </p>
        ))}
        <Bubble align="end" variant="secondary">
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
              className="flex max-w-full flex-col items-end gap-1"
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
                const assistant = messages.some((item) =>
                  ["assistant", "agent"].includes(item.role),
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
                      {messages.map((message) => {
                        const agent = ["assistant", "agent"].includes(
                          message.role,
                        );
                        return (
                          <Message
                            key={message.id}
                            align={agent ? "end" : "start"}
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
                                align={agent ? "end" : "start"}
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
                      {tools.length > 0 && assistant && (
                        <p className="text-right text-xs text-muted-foreground">
                          Tool activity in this exchange. Exact message link not
                          recorded.
                        </p>
                      )}
                      {tools.map((tool) => (
                        <ToolActivity
                          key={tool.id}
                          tool={tool}
                          timeline={timeline}
                          onSelect={onSelect}
                        />
                      ))}
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
