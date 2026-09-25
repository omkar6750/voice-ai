import { ReadOnlyValue } from "@/components/record-page";
import type { AgentConfig } from "./types";

function show(value: unknown): string {
  if (value === null || value === undefined) return "Not set";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function ConfigReadout({
  title,
  value,
}: {
  title: string;
  value: Record<string, unknown>;
}) {
  return (
    <section>
      <h2 className="mb-2 text-base font-semibold">{title}</h2>
      {Object.entries(value).map(([key, item]) => (
        <ReadOnlyValue
          key={key}
          label={key.replaceAll("_", " ")}
          value={show(item)}
        />
      ))}
    </section>
  );
}

export function ContextPanel({ config }: { config: AgentConfig }) {
  return (
    <div className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-8">
        <ConfigReadout
          title="Context pruning"
          value={{
            prune_node_ids: config.context.prune_node_ids,
            remove_transition_tool_pairs:
              config.context.remove_transition_tool_pairs,
          }}
        />
        <ConfigReadout title="Summarizer" value={config.context.summarizer} />
      </div>
      <ConfigReadout title="Classifier" value={config.classifier} />
      <p className="text-xs text-muted-foreground lg:col-span-2">
        Stored defaults shown in full. Cadence jobs need live-run acceptance
        tests before controls become editable here. Model/prompt fields are not
        silently overwritten on save.
      </p>
    </div>
  );
}
