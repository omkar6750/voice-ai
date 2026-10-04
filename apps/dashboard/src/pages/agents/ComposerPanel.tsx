import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useResource } from "@/lib/resources";
import { CredentialBindingSelect, bindCredential } from "./CredentialBindingSelect";
import type { AgentConfig, ProviderCatalog, ToolVersion } from "./types";

const rituDemoPrompt =
  "Write a brief WhatsApp follow-up from Ritu at Neotribe Software Studio. Summarize the caller's actual need and the next step agreed in the call. Use the caller's current language naturally, especially conversational Telugu, Hindi or Marathi when they used it. The hosted link is a voice AI demo, not a demo of the caller's proposed product. Do not promise a proposal, appointment, or work that was not confirmed. Avoid cut-off sentences.";
const genericPrompt =
  "Write a brief WhatsApp follow-up using the caller's actual language. Summarize only the need and next step confirmed in the conversation. Describe links accurately and avoid invented promises or completed actions.";

export function ComposerPanel({ config, change, catalog, disabled }: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  catalog: ProviderCatalog | null;
  disabled: boolean;
}) {
  const composer = config.composer;
  const [selected, setSelected] = useState("");
  const keys = Object.keys(config.tool_bindings);
  const active = selected || Object.keys(composer.templates)[0] || "";
  const template = composer.templates[active];
  const binding = config.tool_bindings[active];
  const versions = useResource<{ versions: ToolVersion[] }>(
    binding ? `/tools/${binding.tool_id}/versions` : "",
    Boolean(binding),
  );
  const pinned = versions.data?.versions.find((version) => version.id === binding?.tool_version_id);
  const isWhatsAppTemplate = pinned?.config.handler === "send_whatsapp_template" && Boolean(pinned.config.whatsapp);
  const model = composer.model;
  const providers = catalog?.providers.filter((item) => item.slots.includes("llm")) ?? [];
  const provider = providers.find((item) => item.provider === model.provider);
  const models = provider?.models_by_slot?.llm ?? provider?.models ?? [];

  function update(partial: Partial<typeof composer>) {
    change({ ...config, composer: { ...composer, ...partial } });
  }

  function updateTemplate(partial: Partial<NonNullable<typeof template>>) {
    update({ templates: { ...composer.templates, [active]: { ...template, ...partial } } });
  }

  return <section className="flex max-w-4xl flex-col gap-6">
    <div>
      <h2 className="text-base font-semibold">WhatsApp composer</h2>
      <p className="text-sm text-muted-foreground">A separate LLM will write only the dynamic fields of each approved template from the full plain Caller/Agent transcript. The main agent will only choose the tool and optional confirmed recipient.</p>
      <p className="mt-2 text-xs text-muted-foreground">When enabled, the selected provider receives the plain Caller/Agent transcript. Tool calls, summaries, and flow instructions are excluded.</p>
    </div>
    <label className="flex items-center gap-2 text-sm font-medium">
      <input type="checkbox" checked={composer.enabled} disabled={disabled} onChange={(event) => update({ enabled: event.target.checked })} />
      Configure composer for this agent
    </label>
    <div className="grid gap-4 sm:grid-cols-2">
      <Field><FieldLabel htmlFor="composer-provider">Provider</FieldLabel>
        <NativeSelect id="composer-provider" value={model.provider} disabled={disabled} onChange={(event) => {
          const nextProvider = event.target.value as typeof model.provider;
          const entry = providers.find((item) => item.provider === nextProvider);
          const firstModel = entry?.models_by_slot?.llm?.[0] ?? entry?.models?.[0] ?? model.model;
          const nextModel = {
            ...model,
            provider: nextProvider,
            model: firstModel,
            reasoning_effort: nextProvider === "isoquant" ? "low" as const : nextProvider === "gemini" || nextProvider === "openrouter" ? "provider_default" as const : "none" as const,
            models: nextProvider === "openrouter" ? model.models : [],
            provider_preferences: nextProvider === "openrouter" ? model.provider_preferences : null,
          };
          change(bindCredential({ ...config, composer: { ...composer, model: nextModel } }, "composer", null));
        }}>
          {providers.map((entry) => <option key={entry.provider} value={entry.provider}>{entry.provider}</option>)}
          {!providers.some((entry) => entry.provider === model.provider) && <option value={model.provider}>{model.provider}</option>}
        </NativeSelect>
      </Field>
      <Field><FieldLabel htmlFor="composer-model">Model</FieldLabel>
        {models.length ? <NativeSelect id="composer-model" value={model.model} disabled={disabled} onChange={(event) => update({ model: { ...model, model: event.target.value } })}>
          <option value="">Select a model</option>
          {!models.includes(model.model) && model.model && <option value={model.model}>{model.model}</option>}
          {models.map((entry) => <option key={entry} value={entry}>{entry}</option>)}
        </NativeSelect> : <Input id="composer-model" value={model.model} disabled={disabled} onChange={(event) => update({ model: { ...model, model: event.target.value } })} />}
      </Field>
      <CredentialBindingSelect stage="composer" provider={model.provider} value={config.credential_refs.composer} disabled={disabled} change={(id) => change(bindCredential(config, "composer", id))} />
      <Field><FieldLabel htmlFor="composer-timeout">Provider timeout (seconds)</FieldLabel><Input id="composer-timeout" type="number" min={1} max={60} value={composer.timeout_secs} disabled={disabled} onChange={(event) => update({ timeout_secs: Number(event.target.value) })} /></Field>
      <Field><FieldLabel htmlFor="composer-temperature">Temperature</FieldLabel><Input id="composer-temperature" type="number" min={0} max={2} step={0.1} value={model.temperature} disabled={disabled} onChange={(event) => update({ model: { ...model, temperature: Number(event.target.value) } })} /></Field>
      <Field><FieldLabel htmlFor="composer-tokens">Maximum output tokens</FieldLabel><Input id="composer-tokens" type="number" min={1} max={2048} value={model.max_tokens} disabled={disabled} onChange={(event) => update({ model: { ...model, max_tokens: Number(event.target.value) } })} /></Field>
    </div>
    <div className="border-t pt-5">
      <h3 className="text-sm font-semibold">Template prompts</h3>
      <p className="text-xs text-muted-foreground">Choose a bound WhatsApp template tool. Each tool gets its own composer instruction and required links.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <NativeSelect aria-label="Bound template tool" className="max-w-sm" value={active} disabled={disabled || !keys.length} onChange={(event) => setSelected(event.target.value)}>
          <option value="">Choose a bound tool</option>
          {keys.map((key) => <option key={key} value={key}>{key}</option>)}
        </NativeSelect>
        {active && !template && <Button type="button" variant="outline" disabled={disabled || !isWhatsAppTemplate} onClick={() => update({ templates: { ...composer.templates, [active]: { system_prompt: active === "whatsapp_template_dialtone_followup" ? rituDemoPrompt : genericPrompt, required_urls: active === "whatsapp_template_dialtone_followup" ? ["https://omkars-voice-ai.netlify.app/"] : [] } } })}>Add composer prompt</Button>}
        {template && <Button type="button" variant="outline" disabled={disabled} onClick={() => {
          const templates = { ...composer.templates }; delete templates[active]; update({ templates });
        }}>Remove prompt</Button>}
      </div>
      {active && !isWhatsAppTemplate && <p className="mt-2 text-xs text-amber-900">Select a bound, published WhatsApp template tool to configure its composer prompt.</p>}
      {template && <div className="mt-5 flex flex-col gap-4">
        <Field><FieldLabel htmlFor="composer-prompt">Composer system prompt for {active}</FieldLabel><Textarea id="composer-prompt" className="min-h-48" value={template.system_prompt} disabled={disabled} onChange={(event) => updateTemplate({ system_prompt: event.target.value })} /><FieldDescription>Give template-specific wording and link meaning. The composer receives only the ordered plain transcript as its user message.</FieldDescription></Field>
        <Field><FieldLabel htmlFor="composer-urls">Required URLs (one per line)</FieldLabel><Textarea id="composer-urls" value={template.required_urls.join("\n")} disabled={disabled} onChange={(event) => updateTemplate({ required_urls: event.target.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean) })} /><FieldDescription>The send will fail if the composed fields omit any required URL.</FieldDescription></Field>
      </div>}
    </div>
  </section>;
}
