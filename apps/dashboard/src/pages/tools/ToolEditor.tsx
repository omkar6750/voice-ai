import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";

type ToolVersion = components["schemas"]["ToolVersionResponse"];
type ToolConfig = components["schemas"]["ToolConfig"];
type HandlerCatalog = components["schemas"]["ToolHandlerCatalog"];
type ValidationResponse = components["schemas"]["ToolValidationResponse"];
type EditableToolConfig = Omit<ToolConfig, "parameters" | "wait"> & {
  parameters: Record<string, unknown>;
  wait: NonNullable<ToolConfig["wait"]>;
};

type ParameterRow = {
  name: string;
  type: string;
  description: string;
  required: boolean;
};

function parameterRows(config: ToolConfig): ParameterRow[] {
  const schema = (config.parameters ?? {}) as {
    properties?: Record<string, { type?: string; description?: string }>;
    required?: string[];
  };
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([name, value]) => ({
    name,
    type: value.type ?? "string",
    description: value.description ?? "",
    required: required.has(name),
  }));
}

function editableConfig(config: ToolConfig): EditableToolConfig {
  return {
    ...config,
    parameters: config.parameters ?? { type: "object", properties: {} },
    wait: config.wait ?? { mode: "silent_wait", acknowledgement: null },
  } as EditableToolConfig;
}

function parametersSchema(rows: ParameterRow[]): Record<string, unknown> {
  const properties: Record<string, Record<string, string>> = {};
  const required: string[] = [];
  for (const row of rows) {
    if (!row.name.trim()) continue;
    properties[row.name.trim()] = {
      type: row.type,
      description: row.description,
    };
    if (row.required) required.push(row.name.trim());
  }
  return {
    type: "object",
    properties,
    ...(required.length ? { required } : {}),
  };
}

function mappingText(value: Record<string, string> | undefined): string {
  return Object.entries(value ?? {})
    .map(([key, target]) => `${key} -> ${target}`)
    .join("\n");
}

function parseMappingText(value: string): Record<string, string> {
  return Object.fromEntries(
    value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [key, ...rest] = line.split("->");
        return [key.trim(), rest.join("->").trim()];
      })
      .filter(([key, target]) => Boolean(key && target)),
  );
}

export function ToolEditor({
  version,
  handlers,
  onSaved,
}: {
  version: ToolVersion;
  handlers: HandlerCatalog["handlers"];
  onSaved: () => Promise<void>;
}) {
  const api = useApi();
  const [config, setConfig] = useState<EditableToolConfig>(() => editableConfig(version.config));
  const [rows, setRows] = useState<ParameterRow[]>(() => parameterRows(version.config));
  const [busy, setBusy] = useState<"save" | "validate" | "publish" | null>(null);
  const [mapping, setMapping] = useState(() =>
    mappingText(version.config.http?.argument_mapping),
  );
  const [extraction, setExtraction] = useState(() =>
    mappingText(version.config.http?.output_extraction),
  );

  const selectedHandler = useMemo(
    () => handlers.find((item) => item.name === config.handler),
    [config.handler, handlers],
  );

  function setField<K extends keyof ToolConfig>(key: K, value: ToolConfig[K]) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  function setWaitField(
    key: "mode" | "acknowledgement",
    value: string | null,
  ) {
    setConfig((current) => ({
      ...current,
      wait: { ...current.wait, [key]: value },
    }));
  }

  function setHttpField(key: string, value: unknown) {
    if (!config.http) return;
    setConfig((current) => ({
      ...current,
      http: { ...current.http!, [key]: value },
    }));
  }

  async function save() {
    setBusy("save");
    try {
      await api(`/tool-versions/${version.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          revision: version.revision,
          config: {
            ...config,
            parameters: parametersSchema(rows),
            ...(config.http
              ? {
                  http: {
                    ...config.http,
                    argument_mapping: parseMappingText(mapping),
                    output_extraction: parseMappingText(extraction),
                  },
                }
              : {}),
          },
        }),
      });
      toast.success("Draft saved");
      await onSaved();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save draft");
    } finally {
      setBusy(null);
    }
  }

  async function validate() {
    setBusy("validate");
    try {
      const result = await api<ValidationResponse>(
        `/tool-versions/${version.id}/validate`,
        { method: "POST" },
      );
      if (result.valid) toast.success("Tool configuration is valid");
      else toast.error((result.issues ?? []).map((issue) => issue.message).join("; "));
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not validate tool");
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    setBusy("publish");
    try {
      await api(`/tool-versions/${version.id}/publish`, {
        method: "POST",
        body: JSON.stringify({ revision: version.revision }),
      });
      toast.success("Tool published");
      await onSaved();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not publish tool");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-4 rounded-lg border bg-muted/20 p-4">
      <FieldGroup>
        <Field>
          <FieldLabel>Tool name</FieldLabel>
          <Input value={config.name} disabled className="font-mono" />
          <FieldDescription>
            The logical tool name is immutable; clone the logical tool to create a different tool.
          </FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor={`tool-description-${version.id}`}>Description</FieldLabel>
          <Textarea
            id={`tool-description-${version.id}`}
            value={config.description}
            onChange={(event) => setField("description", event.target.value)}
            rows={3}
          />
        </Field>
        <Field>
          <FieldLabel>Execution</FieldLabel>
          <Input value={config.kind === "registered" ? "Registered backend handler" : "HTTP request"} disabled />
        </Field>

        {config.kind === "registered" && (
          <>
            <Field>
              <FieldLabel htmlFor={`tool-handler-${version.id}`}>Handler</FieldLabel>
              <NativeSelect
                id={`tool-handler-${version.id}`}
                value={config.handler ?? ""}
                onChange={(event) => {
                  const handler = event.target.value || null;
                  setField("handler", handler);
                  if (handler !== "send_whatsapp_template") setField("whatsapp", null);
                }}
              >
                <NativeSelectOption value="">Select reviewed handler</NativeSelectOption>
                {handlers.map((handler) => (
                  <NativeSelectOption key={handler.name} value={handler.name}>
                    {handler.name}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
              <FieldDescription>{selectedHandler?.description}</FieldDescription>
            </Field>
            {config.handler === "send_whatsapp_template" && config.whatsapp && (
              <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
                WhatsApp template settings are account-scoped and edited from the integration
                template workflow. This draft is linked to template{" "}
                <span className="font-mono text-foreground">{config.whatsapp.template_name}</span>
                {config.whatsapp.header_media_id ? " with a catalog media header." : "."}
              </div>
            )}
            <Field>
              <FieldLabel htmlFor={`tool-wait-${version.id}`}>Wait mode</FieldLabel>
              <NativeSelect
                id={`tool-wait-${version.id}`}
                value={config.wait.mode}
                onChange={(event) => setWaitField("mode", event.target.value)}
              >
                <NativeSelectOption value="silent_wait">Silent wait</NativeSelectOption>
                <NativeSelectOption value="acknowledge_then_wait">Acknowledge, then wait</NativeSelectOption>
                <NativeSelectOption value="continue_conversation">Continue conversation</NativeSelectOption>
              </NativeSelect>
            </Field>
            {config.wait.mode === "acknowledge_then_wait" && (
              <Field>
                <FieldLabel htmlFor={`tool-ack-${version.id}`}>Acknowledgement</FieldLabel>
                <Input
                  id={`tool-ack-${version.id}`}
                  value={config.wait.acknowledgement ?? ""}
                  onChange={(event) => setWaitField("acknowledgement", event.target.value)}
                />
              </Field>
            )}
          </>
        )}

        {config.kind === "http" && config.http && (
          <>
            <Field>
              <FieldLabel htmlFor={`tool-url-${version.id}`}>Endpoint</FieldLabel>
              <Input
                id={`tool-url-${version.id}`}
                value={config.http.url}
                onChange={(event) => setHttpField("url", event.target.value)}
              />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor={`tool-method-${version.id}`}>Method</FieldLabel>
                <NativeSelect
                  id={`tool-method-${version.id}`}
                  value={config.http.method}
                  onChange={(event) => setHttpField("method", event.target.value)}
                >
                  {(["GET", "POST", "PUT", "PATCH", "DELETE"] as const).map((method) => (
                    <NativeSelectOption key={method} value={method}>{method}</NativeSelectOption>
                  ))}
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel htmlFor={`tool-timeout-${version.id}`}>Timeout (seconds)</FieldLabel>
                <Input
                  id={`tool-timeout-${version.id}`}
                  type="number"
                  min={1}
                  max={120}
                  value={config.http.timeout_secs}
                  onChange={(event) => setHttpField("timeout_secs", Number(event.target.value))}
                />
              </Field>
            </div>
            <Field>
              <FieldLabel htmlFor={`tool-secret-${version.id}`}>Secret reference</FieldLabel>
              <Input
                id={`tool-secret-${version.id}`}
                value={config.http.secret_reference ?? ""}
                onChange={(event) => setHttpField("secret_reference", event.target.value || null)}
                placeholder="integration-secret-id"
              />
            </Field>
            <div className="grid gap-4 md:grid-cols-2">
              <Field>
                <FieldLabel htmlFor={`tool-mapping-${version.id}`}>Argument mapping</FieldLabel>
                <Textarea
                  id={`tool-mapping-${version.id}`}
                  value={mapping}
                  onChange={(event) => setMapping(event.target.value)}
                  placeholder="caller_name -> customer_name"
                  rows={4}
                />
                <FieldDescription>One mapping per line: tool argument -&gt; request field.</FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor={`tool-extraction-${version.id}`}>Output extraction</FieldLabel>
                <Textarea
                  id={`tool-extraction-${version.id}`}
                  value={extraction}
                  onChange={(event) => setExtraction(event.target.value)}
                  placeholder="status -> data.status"
                  rows={4}
                />
                <FieldDescription>One mapping per line: result field -&gt; response path.</FieldDescription>
              </Field>
            </div>
          </>
        )}

        <div>
          <div className="mb-2 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium">Input parameters</h3>
              <p className="text-xs text-muted-foreground">These fields become the function-calling schema.</p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => setRows((current) => [...current, { name: "", type: "string", description: "", required: false }])}
            >
              Add parameter
            </Button>
          </div>
          <div className="flex flex-col gap-3">
            {rows.map((row, index) => (
              <div key={`${version.id}-${index}`} className="grid gap-2 rounded-md border p-3 md:grid-cols-[1fr_120px_1.5fr_auto]">
                <Input
                  value={row.name}
                  placeholder="parameter_name"
                  onChange={(event) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item))}
                />
                <NativeSelect
                  value={row.type}
                  onChange={(event) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, type: event.target.value } : item))}
                >
                  {(["string", "number", "integer", "boolean"] as const).map((type) => <NativeSelectOption key={type} value={type}>{type}</NativeSelectOption>)}
                </NativeSelect>
                <Input
                  value={row.description}
                  placeholder="Description"
                  onChange={(event) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, description: event.target.value } : item))}
                />
                <div className="flex items-center gap-2 text-xs">
                  <label className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={row.required}
                      onChange={(event) => setRows((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, required: event.target.checked } : item))}
                    />
                    Required
                  </label>
                  <Button type="button" size="sm" variant="ghost" onClick={() => setRows((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Remove</Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </FieldGroup>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button type="button" disabled={busy !== null} onClick={() => void save()}>
          {busy === "save" ? "Saving…" : "Save draft"}
        </Button>
        <Button type="button" variant="outline" disabled={busy !== null} onClick={() => void validate()}>
          {busy === "validate" ? "Validating…" : "Validate"}
        </Button>
        <Button type="button" variant="secondary" disabled={busy !== null} onClick={() => void publish()}>
          {busy === "publish" ? "Publishing…" : "Publish"}
        </Button>
      </div>
    </div>
  );
}
