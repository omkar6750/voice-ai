import { useEffect, useMemo, useRef, useState } from "react";
import { closeHistory } from "@tiptap/pm/history";
import { EditorContent, useEditor } from "@tiptap/react";
import { Placeholder, UndoRedo } from "@tiptap/extensions";
import { parsePrompt, promptErrors } from "./prompt-templates";
import { FallbackPicker } from "./FallbackPicker";
import { promptDocument, promptExtensions } from "./prompt-document";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Maximize2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

const toolPattern = /#([a-z][a-z0-9_]*)\b/g;

export function PromptEditor({
  id,
  label,
  value,
  onChange,
  availableTools,
  registeredTools,
  availableVariables = [],
  booleanVariables = [],
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
  booleanVariables?: string[];
  placeholder?: string;
  disabled?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const catalog = useRef({
    tools: availableTools,
    variables: availableVariables,
    booleans: booleanVariables,
  });
  catalog.current = {
    tools: availableTools,
    variables: availableVariables,
    booleans: booleanVariables,
  };
  const extensions = useMemo(
    () => [
      ...promptExtensions(() => catalog.current),
      UndoRedo,
      Placeholder.configure({
        placeholder: placeholder ?? "Write the agent’s instructions…",
      }),
    ],
    [placeholder],
  );
  const editor = useEditor(
    {
      extensions,
      content: promptDocument(value),
      editable: !disabled,
      immediatelyRender: false,
      shouldRerenderOnTransaction: false,
      onUpdate: ({ editor }) => {
        if (!editor.isDestroyed)
          onChange(editor.getText({ blockSeparator: "\n" }));
      },
      editorProps: {
        attributes: {
          id,
          role: "textbox",
          "aria-multiline": "true",
          "aria-labelledby": `${id}-label`,
          spellcheck: "false",
          class:
            "min-h-48 max-h-[36rem] overflow-y-auto [scrollbar-width:thin] [scrollbar-color:var(--border)_transparent] [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/30 [&::-webkit-scrollbar-track]:bg-transparent whitespace-pre-wrap break-words rounded-lg border border-input bg-transparent px-3 py-2 font-mono text-sm leading-6 text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-disabled:cursor-not-allowed aria-disabled:opacity-50 [&_.is-empty]:before:pointer-events-none [&_.is-empty]:before:float-left [&_.is-empty]:before:h-0 [&_.is-empty]:before:text-muted-foreground [&_.is-empty]:before:content-[attr(data-placeholder)]",
        },
      },
    },
    [id, extensions],
  );
  // useEditor can destroy an old instance in its effect before these effects run
  // when the node id or extensions change. Never read that stale instance.
  // Parent echoes never replace the document or move its selection.
  useEffect(() => {
    if (
      editor &&
      !editor.isDestroyed &&
      editor.getText({ blockSeparator: "\n" }) !== value
    ) {
      editor
        .chain()
        .setContent(promptDocument(value), { emitUpdate: false })
        .setMeta("addToHistory", false)
        .run();
      editor.view.dispatch(closeHistory(editor.state.tr));
    }
  }, [editor, value]);
  useEffect(() => {
    if (editor && !editor.isDestroyed) editor.setEditable(!disabled, false);
  }, [editor, disabled]);
  const catalogKey = JSON.stringify([
    availableTools,
    availableVariables,
    booleanVariables,
  ]);
  useEffect(() => {
    if (editor && !editor.isDestroyed)
      editor.view.dispatch(editor.state.tr.setMeta("prompt-catalog", true));
  }, [editor, catalogKey]);
  const roughTokens = Math.ceil(new TextEncoder().encode(value).length / 4);

  // Tool references
  const toolReferences = [...value.matchAll(toolPattern)].map(
    (match) => match[1],
  );
  const unresolvedTools = [
    ...new Set(toolReferences.filter((name) => !availableTools.includes(name))),
  ];

  // Variable references
  let variableReferences: string[] = [];
  try {
    variableReferences = parsePrompt(value)
      .filter((t) => !t.escaped)
      .flatMap((t) => t.keys);
  } catch {
    /* validation below */
  }
  const usedVariables = [...new Set(variableReferences)];
  const unresolvedVariables = promptErrors(
    value,
    availableVariables,
    booleanVariables,
  );

  function insertReference(token: string) {
    if (disabled || !editor || editor.isDestroyed) return;
    editor.chain().focus().insertContent({ type: "text", text: token }).run();
  }

  const hasErrors =
    unresolvedTools.length > 0 || unresolvedVariables.length > 0;

  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.view.dom.setAttribute("aria-invalid", String(hasErrors));
    editor.view.dom.setAttribute("aria-disabled", String(disabled));
  }, [editor, hasErrors, disabled]);

  return (
    <Field data-invalid={hasErrors || undefined}>
      <div className="flex items-center justify-between gap-2">
        <FallbackPicker
          variables={availableVariables.filter(
            (v) => !booleanVariables.includes(v),
          )}
          disabled={disabled}
          insert={insertReference}
        />
        <FieldLabel id={`${id}-label`} htmlFor={id}>
          {label}
        </FieldLabel>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Expand ${label}`}
          onClick={() => setExpanded(true)}
        >
          <Maximize2 />
        </Button>
      </div>
      {!expanded && <EditorContent editor={editor} />}
      <Dialog open={expanded} onOpenChange={setExpanded}>
        <DialogContent className="max-h-[90svh] w-[calc(100%-2rem)] max-w-7xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>
              Edit the same prompt in an expanded view. Changes remain in your
              draft until saved.
            </DialogDescription>
          </DialogHeader>
          {expanded && (
            <EditorContent
              editor={editor}
              className="[&_.tiptap]:min-h-[45svh] [&_.tiptap]:max-h-[65svh]"
            />
          )}
          <dl className="flex gap-5 text-xs">
            <div className="flex gap-2">
              <dt className="text-muted-foreground">Chars</dt>
              <dd>{value.length.toLocaleString()}</dd>
            </div>
            <div className="flex gap-2">
              <dt className="text-muted-foreground">Tokens</dt>
              <dd>~{roughTokens.toLocaleString()}</dd>
            </div>
          </dl>
        </DialogContent>
      </Dialog>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <FieldDescription>
          Insert <code>#tools</code> and <code>{"{{ variables }}"}</code>.
        </FieldDescription>
        <dl
          className="flex gap-4 text-xs"
          title="Tokens are estimated; model usage also includes context and tools."
        >
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Chars</dt>
            <dd className="font-medium tabular-nums">
              {value.length.toLocaleString()}
            </dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-muted-foreground">Tokens</dt>
            <dd className="font-medium tabular-nums">
              ~{roughTokens.toLocaleString()}
            </dd>
          </div>
        </dl>
      </div>

      {unresolvedTools.length > 0 && (
        <p className="text-xs text-destructive">
          Unbound tool references:{" "}
          {unresolvedTools.map((name) => `#${name}`).join(", ")}.{" "}
          {unresolvedTools.some((name) => registeredTools.includes(name))
            ? "Bind published tool versions first."
            : "Check tool registry and spelling."}
        </p>
      )}

      {unresolvedVariables.length > 0 && (
        <p className="text-xs text-destructive">
          Prompt expression errors: {unresolvedVariables.join("; ")}. Use an
          available time variable, configured contact field or conversation fact
          key.
        </p>
      )}

      {availableVariables.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="font-medium">Variables (click to insert)</span>
            <span>
              {
                usedVariables.filter((v) => availableVariables.includes(v))
                  .length
              }{" "}
              / {availableVariables.length} active
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {availableVariables.map((name) => {
              const isUsed = usedVariables.includes(name);
              return (
                <Button
                  key={name}
                  type="button"
                  variant={isUsed ? "highlight" : "outline"}
                  size="sm"
                  disabled={disabled || !editor || editor.isDestroyed}
                  className="font-mono"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => insertReference(`{{ ${name} }}`)}
                  title={`Insert {{ ${name} }} at the cursor`}
                >
                  {isUsed ? "✓ " : ""}
                  {`{{ ${name} }}`}
                </Button>
              );
            })}
          </div>
        </div>
      )}

      {availableTools.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium text-muted-foreground">
            Available tools
          </span>
          <div className="flex flex-wrap gap-1">
            {availableTools.map((name) => (
              <Button
                key={name}
                type="button"
                variant="outline"
                size="sm"
                disabled={disabled || !editor || editor.isDestroyed}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => insertReference(`#${name}`)}
                title={`Insert #${name} at the cursor`}
              >
                #{name}
              </Button>
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
    ...new Set(
      parsePrompt(value)
        .filter((t) => !t.escaped)
        .flatMap((t) => t.keys),
    ),
  ];
}
