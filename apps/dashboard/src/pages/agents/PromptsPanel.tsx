import { useState } from "react";
import { Plus, X } from "lucide-react";
import { ReadOnlyValue } from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PromptEditor } from "./PromptEditor";
import type { AgentConfig, ContactVariablesResponse } from "./types";

export function PromptsPanel({
  config,
  change,
  boundTools,
  registeredTools,
  variablesCatalog,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  boundTools: string[];
  registeredTools: string[];
  variablesCatalog?: ContactVariablesResponse | null;
  disabled: boolean;
}) {
  const [customVar, setCustomVar] = useState("");

  const contactVariables = config.contact_variables ?? [];

  const temporalKeys = (variablesCatalog?.temporal ?? []).map((t) => t.key);

  const availableVariables = [
    ...temporalKeys,
    ...contactVariables,
    ...contactVariables.map((v) => `contact.${v}`),
  ];

  function toggleContactVar(key: string) {
    if (disabled) return;
    const next = contactVariables.includes(key)
      ? contactVariables.filter((k) => k !== key)
      : [...contactVariables, key];
    change({ ...config, contact_variables: next });
  }

  function addCustomVar(e?: React.FormEvent) {
    if (e) e.preventDefault();
    const clean = customVar.trim().toLowerCase().replace(/[^a-z0-9_.]+/g, "_");
    if (!clean || contactVariables.includes(clean)) return;
    change({ ...config, contact_variables: [...contactVariables, clean] });
    setCustomVar("");
  }

  function removeContactVar(key: string) {
    if (disabled) return;
    change({
      ...config,
      contact_variables: contactVariables.filter((k) => k !== key),
    });
  }

  function updateGreeting(greeting: string) {
    const nextFlow = greeting.trim()
      ? {
          ...config.flow,
          nodes: config.flow.nodes.map((node) =>
            node.id === config.flow.initial_node
              ? { ...node, respond_immediately: false }
              : node,
          ),
        }
      : config.flow;
    change({ ...config, greeting, flow: nextFlow });
  }

  return (
    <section className="flex max-w-3xl flex-col gap-6">
      <FieldGroup>
        <PromptEditor
          id="system-prompt"
          label="Global system prompt"
          value={config.system_prompt}
          onChange={(system_prompt) => change({ ...config, system_prompt })}
          availableTools={boundTools}
          registeredTools={registeredTools}
          availableVariables={availableVariables}
          disabled={disabled}
        />
        <PromptEditor
          id="greeting"
          label="Verbatim opening"
          value={config.greeting}
          placeholder="Example: Hello, I’m calling about {{ product }}. Do you have two minutes to talk?"
          onChange={updateGreeting}
          availableTools={boundTools}
          registeredTools={registeredTools}
          availableVariables={availableVariables}
          disabled={disabled}
        />
        <p className="text-xs text-muted-foreground">
          Spoken exactly as written before the first LLM turn. Use approved contact or temporal variables with{" "}
          <code className="mx-1">{"{{variable}}"}</code>. Do not repeat this opening in the initial node prompt.
        </p>
      </FieldGroup>

      <section className="flex flex-col gap-3 rounded-lg border p-4">
        <div>
          <h2 className="text-sm font-semibold">Contact & Ad Variables</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Selectively expose caller details and ad metadata to this agent's prompts. Unselected fields (such as phone numbers or internal IDs) are never exposed.
          </p>
        </div>

        {/* Contact table columns introspected from DB */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            Contact Columns (from DB schema):
          </span>
          <div className="flex flex-wrap gap-2">
            {(variablesCatalog?.columns ?? []).map((item) => {
              const isEnabled = contactVariables.includes(item.key);
              return (
                <Badge
                  key={item.key}
                  variant={isEnabled ? "default" : "outline"}
                  className={`cursor-pointer select-none transition-all ${
                    isEnabled
                      ? "bg-primary font-medium text-primary-foreground"
                      : "border-dashed text-muted-foreground hover:border-solid hover:text-foreground"
                  }`}
                  onClick={() => toggleContactVar(item.key)}
                  title={isEnabled ? "Enabled (click to disable)" : `Click to enable (${item.description || item.key})`}
                >
                  {isEnabled ? "✓ " : "+ "}{item.label} ({item.key})
                </Badge>
              );
            })}
          </div>
        </div>

        {/* Discovered metadata keys from existing DB contacts */}
        {variablesCatalog?.metadata_keys && variablesCatalog.metadata_keys.length > 0 && (
          <div className="flex flex-col gap-1.5 pt-2 border-t">
            <span className="text-xs font-medium text-muted-foreground">
              Ad & Lead Metadata (from DB contacts):
            </span>
            <div className="flex flex-wrap gap-2">
              {variablesCatalog.metadata_keys.map((item) => {
                const isEnabled = contactVariables.includes(item.key);
                return (
                  <Badge
                    key={item.key}
                    variant={isEnabled ? "default" : "outline"}
                    className={`cursor-pointer select-none transition-all ${
                      isEnabled
                        ? "bg-primary font-medium text-primary-foreground"
                        : "border-dashed text-muted-foreground hover:border-solid hover:text-foreground"
                    }`}
                    onClick={() => toggleContactVar(item.key)}
                    title={isEnabled ? "Enabled (click to disable)" : `Click to enable (${item.description || item.key})`}
                  >
                    {isEnabled ? "✓ " : "+ "}{item.label} ({item.key})
                  </Badge>
                );
              })}
            </div>
          </div>
        )}

        <form onSubmit={addCustomVar} className="flex items-center gap-2 pt-2 border-t">
          <Input
            placeholder="Custom ad/lead variable (e.g. campaign, ad_headline, budget)"
            value={customVar}
            onChange={(e) => setCustomVar(e.target.value)}
            disabled={disabled}
            className="max-w-xs text-xs"
          />
          <Button
            type="submit"
            variant="outline"
            size="sm"
            disabled={disabled || !customVar.trim()}
          >
            <Plus className="size-3.5" />
            Add metadata variable
          </Button>
        </form>

        {contactVariables.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t text-xs">
            <span className="text-muted-foreground font-medium mr-1">Active in prompts:</span>
            {contactVariables.map((key) => (
              <Badge key={key} variant="secondary" className="gap-1 pr-1 text-xs">
                <code>{`{{ ${key} }}`}</code>
                {!disabled && (
                  <button
                    type="button"
                    onClick={() => removeContactVar(key)}
                    className="hover:text-destructive cursor-pointer rounded-full p-0.5"
                    aria-label={`Remove ${key}`}
                  >
                    <X className="size-3" />
                  </button>
                )}
              </Badge>
            ))}
          </div>
        )}
      </section>

      <div>
        <h2 className="text-sm font-semibold">Current language settings</h2>
        <ReadOnlyValue
          label="Default language"
          value={config.language.default_language}
          reason="Language controls are stored, but call-path application needs acceptance tests."
        />
        <ReadOnlyValue
          label="Supported languages"
          value={config.language.supported_languages.join(", ")}
        />
      </div>
    </section>
  );
}
