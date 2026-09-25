import { useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";

const callPattern = /\b([a-z][a-z0-9_]*)\s*(?=\()/g;

export function PromptEditor({
  id,
  label,
  value,
  onChange,
  availableTools,
  registeredTools,
  disabled = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  availableTools: string[];
  registeredTools: string[];
  disabled?: boolean;
}) {
  const mirror = useRef<HTMLPreElement>(null);
  const references = [...value.matchAll(callPattern)].map((match) => match[1]);
  const unresolved = [
    ...new Set(references.filter((name) => !availableTools.includes(name))),
  ];
  const segments: { text: string; tool?: string }[] = [];
  let start = 0;
  for (const match of value.matchAll(callPattern)) {
    segments.push({ text: value.slice(start, match.index) });
    segments.push({ text: match[1], tool: match[1] });
    start = match.index + match[1].length;
  }
  segments.push({ text: value.slice(start) });

  return (
    <Field data-invalid={unresolved.length > 0 || undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <div className="relative font-mono text-sm">
        <pre
          ref={mirror}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words rounded-md border border-transparent px-3 py-2 leading-6 text-foreground"
        >
          {segments.map((segment, index) =>
            segment.tool ? (
              <span
                key={index}
                className={
                  availableTools.includes(segment.tool)
                    ? "font-semibold text-primary"
                    : "font-semibold text-destructive"
                }
              >
                {segment.text}
              </span>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
          {"\u200b"}
        </pre>
        <Textarea
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onScroll={(event) => {
            if (mirror.current)
              mirror.current.scrollTop = event.currentTarget.scrollTop;
          }}
          disabled={disabled}
          aria-invalid={unresolved.length > 0}
          spellCheck={false}
          className="relative min-h-48 resize-y whitespace-pre-wrap bg-transparent font-mono leading-6 text-transparent caret-foreground selection:bg-primary/20"
        />
      </div>
      <FieldDescription>
        Tool calls use function syntax such as{" "}
        <code>change_node(node='closing')</code>. Highlighted names match this
        agent's bindings.
      </FieldDescription>
      {unresolved.length > 0 && (
        <p className="text-xs text-destructive">
          Unbound tool references: {unresolved.join(", ")}.{" "}
          {unresolved.some((name) => registeredTools.includes(name))
            ? "Bind published tool versions first."
            : "Check tool registry and spelling."}
        </p>
      )}
      {availableTools.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {availableTools.map((name) => (
            <Badge key={name} variant="secondary">
              {name}
            </Badge>
          ))}
        </div>
      )}
    </Field>
  );
}

export function promptToolReferences(value: string) {
  return [
    ...new Set([...value.matchAll(callPattern)].map((match) => match[1])),
  ];
}
