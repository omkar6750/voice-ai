import { useState } from "react";
import { Transcript } from "@/pages/runs/transcript";
import type { Timeline, Selection } from "@/pages/runs/types";
import { StatusBadge } from "@/pages/runs/status";

const at = "2026-10-09T10:00:00Z";
const timeline: Timeline = {
  run: {
    id: "demo-run",
    status: "completed",
    agent_id: "demo-agent",
    agent_version_id: "demo-v1",
  },
  call: null,
  exchanges: [
    {
      id: "demo-exchange",
      sequence: 1,
      origin: "opening",
      status: "completed",
      created_at: at,
      ended_at: at,
    },
  ],
  messages: [
    {
      role: "assistant",
      content: "Hello! What would you like to explore today?",
    },
    {
      role: "user",
      content: "We want to qualify sales enquiries and arrange follow-ups.",
    },
    {
      role: "assistant",
      content: "What does your team need to know before a follow-up?",
    },
    {
      role: "user",
      content: "Their use case, timeline and the best time to call.",
    },
    {
      role: "assistant",
      content: "Great. We can build that into the qualification flow.",
    },
  ].map((message, index) => ({
    ...message,
    id: `demo-message-${index}`,
    exchange_id: "demo-exchange",
    sequence: index,
    interrupted: false,
    created_at: at,
    source_at: at,
    playback_started_at: null,
    playback_ended_at: null,
  })),
  spans: [],
  tools: [],
  tool_results: [],
  tool_context_deliveries: [],
  classifier_results: [],
  classifier_context_deliveries: [],
  context_events: [],
  interruptions: [],
  diagnostics: [],
  flow_visits: [],
};

export default function RunPreview() {
  const [selected, setSelected] = useState<Selection | null>(null);
  return (
    <div className="rounded-xl border border-border bg-background p-4 md:p-6">
      <div className="mb-5 flex items-center justify-between gap-4">
        <div>
          <p className="text-xs text-muted-foreground">Runs / Fictional demo</p>
          <h3 className="mt-2 text-xl font-semibold">
            Conversation transcript
          </h3>
        </div>
        <StatusBadge status="completed" />
      </div>
      <Transcript timeline={timeline} active={false} onSelect={setSelected} />
      <p aria-live="polite" className="mt-3 text-xs text-muted-foreground">
        {selected
          ? `Selected ${selected.kind}${"id" in selected ? ": " + selected.id : ""}`
          : "Actual Runs transcript component · Fictional sample conversation"}
      </p>
    </div>
  );
}
