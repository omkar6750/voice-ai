import { useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";

const toolPattern = /#([a-z][a-z0-9_]*)\b/g;
const variablePattern = /\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}/g;
const tokenPattern = /(?:#([a-z][a-z0-9_]*)\b)|(?:\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\})/g;

export function PromptEditor({
  id,
  label,
  value,
  onChange,
  availableTools,
  registeredTools,
  availableVariables = [],
  placeholder,
  disabled = false,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (next: string) => void;
  availableTools: string[];
  registeredTools: string[];
  availableVariables?: string[];
  placeholder?: string;
  disabled?: boolean;
}) {
  const mirror = useRef<HTMLPreElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Tool references
  const toolReferences = [...value.matchAll(toolPattern)].map((match) => match[1]);
  const unresolvedTools = [
    ...new Set(toolReferences.filter((name) => !availableTools.includes(name))),
  ];

  // Variable references
  const variableReferences = [...value.matchAll(variablePattern)].map((match) => match[1]);
  const usedVariables = [...new Set(variableReferences)];
  const unresolvedVariables = [
    ...new Set(variableReferences.filter((name) => !availableVariables.includes(name))),
  ];

  // Tokenize value for overlay highlighting
  const segments: { text: string; tool?: string; variable?: string }[] = [];
  let start = 0;
  for (const match of value.matchAll(tokenPattern)) {
    if (match.index > start) {
      segments.push({ text: value.slice(start, match.index) });
    }
    if (match[1]) {
      // #tool_name
      segments.push({ text: match[0], tool: match[1] });
    } else if (match[2]) {
      // {{ variable_name }}
      segments.push({ text: match[0], variable: match[2] });
    }
    start = match.index + match[0].length;
  }
  if (start < value.length) {
    segments.push({ text: value.slice(start) });
  }

  function insertVariable(varName: string) {
    if (disabled) return;
    const token = `{{ ${varName} }}`;
    const el = textareaRef.current;
    if (!el) {
      onChange(value ? `${value} ${token}` : token);
      return;
    }
    const selStart = el.selectionStart ?? value.length;
    const selEnd = el.selectionEnd ?? value.length;
    const next = value.slice(0, selStart) + token + value.slice(selEnd);
    onChange(next);
    setTimeout(() => {
      el.focus();
      const pos = selStart + token.length;
      el.setSelectionRange(pos, pos);
    }, 0);
  }

  const hasErrors = unresolvedTools.length > 0 || unresolvedVariables.length > 0;

  return (
    <Field data-invalid={hasErrors || undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <div className="relative font-mono text-sm">
        <pre
          ref={mirror}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 overflow-hidden whitespace-pre-wrap break-words rounded-md border border-transparent px-3 py-2 leading-6 text-foreground"
        >
          {segments.map((segment, index) => {
            if (segment.tool) {
              const isBound = availableTools.includes(segment.tool);
              return (
                <span
                  key={index}
                  className={
                    isBound
                      ? "font-semibold text-primary"
                      : "font-semibold text-destructive underline decoration-wavy"
                  }
                >
                  {segment.text}
                </span>
              );
            }
            if (segment.variable) {
              const isValid = availableVariables.includes(segment.variable);
              return (
                <span
                  key={index}
                  className={
                    isValid
                      ? "rounded bg-primary/20 px-1 font-semibold text-primary"
                      : "rounded bg-destructive/20 px-1 font-semibold text-destructive underline decoration-wavy"
                  }
                >
                  {segment.text}
                </span>
              );
            }
            return <span key={index}>{segment.text}</span>;
          })}
          {"\u200b"}
        </pre>
        <Textarea
          id={id}
          ref={textareaRef}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onScroll={(event) => {
            if (mirror.current)
              mirror.current.scrollTop = event.currentTarget.scrollTop;
          }}
          disabled={disabled}
          placeholder={placeholder}
          aria-invalid={hasErrors}
          spellCheck={false}
          className="relative min-h-48 resize-y whitespace-pre-wrap bg-transparent font-mono leading-6 text-transparent caret-foreground selection:bg-primary/20"
        />
      </div>

      <FieldDescription>
        Use <code>#tool_name</code> to invoke tools and <code>{"{{ variable }}"}</code> for dynamic contact & temporal fields.
      </FieldDescription>

      {unresolvedTools.length > 0 && (
        <p className="text-xs text-destructive">
          Unbound tool references: {unresolvedTools.map((name) => `#${name}`).join(", ")}.{" "}
          {unresolvedTools.some((name) => registeredTools.includes(name))
            ? "Bind published tool versions first."
            : "Check tool registry and spelling."}
        </p>
      )}

      {unresolvedVariables.length > 0 && (
        <p className="text-xs text-destructive">
          Unbound variable references: {unresolvedVariables.map((name) => `{{ ${name} }}`).join(", ")}.{" "}
          Ensure variables match available temporal tags or configured contact variables.
        </p>
      )}

      {availableVariables.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-medium">Variables (click to insert)</span>
            <span>
              {usedVariables.filter((v) => availableVariables.includes(v)).length} / {availableVariables.length} active
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {availableVariables.map((name) => {
              const isUsed = usedVariables.includes(name);
              return (
                <Badge
                  key={name}
                  variant={isUsed ? "default" : "outline"}
                  className={`cursor-pointer select-none transition-all ${
                    isUsed
                      ? "bg-primary font-medium text-primary-foreground shadow-xs"
                      : "border-dashed text-muted-foreground hover:border-solid hover:text-foreground"
                  }`}
                  onClick={() => insertVariable(name)}
                  title={isUsed ? `Used in prompt (click to insert again)` : `Click to insert {{ ${name} }}`}
                >
                  {isUsed ? "✓ " : ""}{`{{ ${name} }}`}
                </Badge>
              );
            })}
          </div>
        </div>
      )}

      {availableTools.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">Bound tools</span>
          <div className="flex flex-wrap gap-1">
            {availableTools.map((name) => (
              <Badge key={name} variant="secondary">
                #{name}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Field>
  );
}

export function promptToolReferences(value: string) {
  return [
    ...new Set([...value.matchAll(toolPattern)].map((match) => match[1])),
  ];
}

export function promptVariableReferences(value: string) {
  return [
    ...new Set([...value.matchAll(variablePattern)].map((match) => match[1])),
  ];
}
