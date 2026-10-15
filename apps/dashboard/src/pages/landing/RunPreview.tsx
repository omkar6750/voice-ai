import { Bot, UserRound } from "lucide-react";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageHeader,
} from "@/components/ui/message";
import { StatusBadge } from "@/pages/runs/status";

const conversation = [
  {
    agent: true,
    text: "Hi Alex! What would make follow-ups better for your team?",
  },
  { agent: false, text: "Knowing what each caller needs before we call back." },
  {
    agent: true,
    text: "Got it. Let’s find the right next step, at a time that works for you.",
  },
];

export default function RunPreview() {
  return (
    <div className="min-w-0 border border-border bg-card p-4 sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium">A conversation, not a script.</h3>
        <StatusBadge status="completed" />
      </div>
      <div
        className="flex flex-col gap-3"
        aria-label="Sample voice conversation"
      >
        {conversation.map(({ agent, text }, index) => (
          <Message key={index} align={agent ? "start" : "end"}>
            <MessageAvatar>
              {agent ? (
                <Bot aria-hidden="true" className="size-3.5" />
              ) : (
                <UserRound aria-hidden="true" className="size-3.5" />
              )}
            </MessageAvatar>
            <MessageContent className="gap-1.5">
              <MessageHeader>{agent ? "Agent" : "Caller"}</MessageHeader>
              <Bubble variant={agent ? "default" : "secondary"}>
                <BubbleContent className="text-xs leading-5 sm:text-sm">
                  {text}
                </BubbleContent>
              </Bubble>
            </MessageContent>
          </Message>
        ))}
      </div>
    </div>
  );
}
