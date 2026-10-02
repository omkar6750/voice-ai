import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useBlocker, useSearchParams } from "react-router-dom";
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
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  parameterRows,
  parametersSchema,
  parseSchema,
  type ParameterRow,
} from "./authoring";
const WhatsAppMediaPicker = lazy(() =>
  import("@/pages/integrations/WhatsAppMediaPicker").then((module) => ({
    default: module.WhatsAppMediaPicker,
  })),
);

type ToolVersion = components["schemas"]["ToolVersionResponse"];
type ToolConfig = components["schemas"]["ToolConfig"];
type HandlerCatalog = components["schemas"]["ToolHandlerCatalog"];
type ValidationResponse = components["schemas"]["ToolValidationResponse"];
type WhatsAppConfig = NonNullable<ToolConfig["whatsapp"]>;
type EditableToolConfig = Omit<ToolConfig, "parameters"> & {
  parameters: Record<string, unknown>;
};

function editableConfig(config: ToolConfig): EditableToolConfig {
  return {
    ...config,
    parameters: config.parameters ?? { type: "object", properties: {} },
  } as EditableToolConfig;
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
  onSectionChange,
  onConflict,
  onDirtyChange,
}: {
  version: ToolVersion;
  handlers: HandlerCatalog["handlers"];
  onSaved: (version: ToolVersion) => void;
  onSectionChange: (section: string) => void;
  onConflict: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const api = useApi();
  const [config, setConfig] = useState<EditableToolConfig>(() =>
    editableConfig(version.config),
  );
  const [rows, setRows] = useState<ParameterRow[]>(() =>
    parameterRows(version.config.parameters ?? {}),
  );
  const [busy, setBusy] = useState<"save" | "validate" | null>(null);
  const [mapping, setMapping] = useState(() =>
    mappingText(version.config.http?.argument_mapping),
  );
  const [extraction, setExtraction] = useState(() =>
    mappingText(version.config.http?.output_extraction),
  );
  const [whatsappMapping, setWhatsappMapping] = useState(() =>
    mappingText(version.config.whatsapp?.parameter_mappings),
  );

  const [params, setParams] = useSearchParams();
  const section = [
    "definition",
    "parameters",
    "execution",
    "advanced",
  ].includes(params.get("section") ?? "")
    ? params.get("section")!
    : "definition";
  const [schemaText, setSchemaText] = useState(() =>
    JSON.stringify(
      version.config.parameters ?? { type: "object", properties: {} },
      null,
      2,
    ),
  );
  const [schemaEdited, setSchemaEdited] = useState(false);
  const [revision, setRevision] = useState(version.revision);
  const [conflict, setConflict] = useState(false);
  const [reloadOpen, setReloadOpen] = useState(false);
  const saving = useRef(false);
  const fingerprint = JSON.stringify([
    config,
    rows,
    mapping,
    extraction,
    whatsappMapping,
    schemaEdited ? schemaText : null,
    schemaEdited,
  ]);
  const [savedFingerprint, setSavedFingerprint] = useState(fingerprint);
  const dirty = fingerprint !== savedFingerprint;
  const locked = version.status !== "draft";
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      (dirty || busy !== null) &&
      currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    onSectionChange(section);
  }, [section, onSectionChange]);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function adopt(next: ToolVersion) {
    const nextConfig = editableConfig(next.config);
    const nextRows = parameterRows(nextConfig.parameters);
    const nextMapping = mappingText(nextConfig.http?.argument_mapping);
    const nextExtraction = mappingText(nextConfig.http?.output_extraction);
    const nextWhatsapp = mappingText(nextConfig.whatsapp?.parameter_mappings);
    const nextSchema = JSON.stringify(nextConfig.parameters, null, 2);
    setConfig(nextConfig);
    setRows(nextRows);
    setMapping(nextMapping);
    setExtraction(nextExtraction);
    setWhatsappMapping(nextWhatsapp);
    setSchemaText(nextSchema);
    setSchemaEdited(false);
    setRevision(next.revision);
    setConflict(false);
    setSavedFingerprint(
      JSON.stringify([
        nextConfig,
        nextRows,
        nextMapping,
        nextExtraction,
        nextWhatsapp,
        null,
        false,
      ]),
    );
  }
  useEffect(() => {
    if (!dirty && !busy && version.revision > revision) adopt(version);
  }, [version, dirty, busy, revision]);
  function changeSection(next: string) {
    // Apply JSON before returning to structured fields; invalid JSON stays visible.
    if (section === "advanced" && schemaEdited) {
      try {
        const schema = parseSchema(schemaText);
        setConfig((current) => ({ ...current, parameters: schema }));
        setRows(parameterRows(schema));
        setSchemaEdited(false);
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : "Invalid schema");
        return;
      }
    }
    const nextParams = new URLSearchParams(params);
    nextParams.set("section", next);
    setParams(nextParams, { replace: true });
    if (next === "advanced" && !schemaEdited) {
      try {
        setSchemaText(
          JSON.stringify(parametersSchema(rows, config.parameters), null, 2),
        );
      } catch (cause) {
        toast.error(
          cause instanceof Error ? cause.message : "Invalid parameters",
        );
      }
    }
  }

  const selectedHandler = useMemo(
    () => handlers.find((item) => item.name === config.handler),
    [config.handler, handlers],
  );

  function setField<K extends keyof ToolConfig>(key: K, value: ToolConfig[K]) {
    setConfig((current) => ({ ...current, [key]: value }));
  }

  function setHttpField(key: string, value: unknown) {
    if (!config.http) return;
    setConfig((current) => ({
      ...current,
      http: { ...current.http!, [key]: value },
    }));
  }

  async function save(): Promise<boolean> {
    if (saving.current || conflict || locked) return false;
    saving.current = true;
    setBusy("save");
    try {
      const nextConfig = {
        ...config,
        parameters: schemaEdited
          ? parseSchema(schemaText)
          : parametersSchema(rows, config.parameters),
        ...(config.whatsapp
          ? {
              whatsapp: {
                ...config.whatsapp,
                parameter_mappings: parseMappingText(whatsappMapping),
              },
            }
          : {}),
        ...(config.http
          ? {
              http: {
                ...config.http,
                argument_mapping: parseMappingText(mapping),
                output_extraction: parseMappingText(extraction),
              },
            }
          : {}),
      };
      const saved = await api<
        components["schemas"]["ToolVersionMutationResponse"]
      >("/tool-versions/" + version.id, {
        method: "PATCH",
        body: JSON.stringify({ revision, config: nextConfig }),
      });
      if (!saved.config || saved.revision == null)
        throw new Error("Save returned an incomplete version.");
      const next = {
        ...version,
        revision: saved.revision,
        config: saved.config,
      };
      adopt(next);
      onSaved(next);
      toast.success("Draft saved");
      return true;
    } catch (cause) {
      if (
        cause instanceof Error &&
        /changed|409|immutable/i.test(cause.message)
      ) {
        setConflict(true);
        onConflict();
      }
      toast.error(
        cause instanceof Error ? cause.message : "Could not save draft",
      );
      return false;
    } finally {
      saving.current = false;
      setBusy(null);
    }
  }

  async function validate() {
    if (locked) return;
    // Validation uses the persisted configuration, so save dirty input first.
    if (dirty && !(await save())) return;
    setBusy("validate");
    try {
      const result = await api<ValidationResponse>(
        "/tool-versions/" + version.id + "/validate",
        { method: "POST" },
      );
      if (result.valid) toast.success("Saved tool configuration is valid");
      else
        toast.error(
          (result.issues ?? []).map((issue) => issue.message).join("; "),
        );
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not validate tool",
      );
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="sticky top-0 flex flex-wrap items-center justify-between gap-3 bg-background py-3">
        <p className="text-sm text-muted-foreground">
          Revision {revision} · {dirty ? "Unsaved changes" : "Saved"}
        </p>
        <div className="flex gap-2">
          <Button
            variant="outline"
            disabled={busy !== null || conflict || locked}
            onClick={() => void validate()}
          >
            Save & validate
          </Button>
          <Button
            disabled={busy !== null || conflict || locked || !dirty}
            onClick={() => void save()}
          >
            {busy === "save" ? "Saving…" : "Save draft"}
          </Button>
        </div>
      </div>
      {locked && (
        <Alert>
          <AlertTitle>This version was published</AlertTitle>
          <AlertDescription>
            Your unsaved edits are preserved for inspection. This immutable
            version cannot be saved or changed.
          </AlertDescription>
        </Alert>
      )}
      {conflict && (
        <Alert variant="destructive">
          <AlertTitle>This draft changed</AlertTitle>
          <AlertDescription>
            Your edits are preserved. Reload the stored version before editing
            again.
            <Button variant="outline" onClick={() => setReloadOpen(true)}>
              Review stored version
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <Tabs value={section} onValueChange={changeSection}>
        <TabsList variant="line">
          <TabsTrigger value="definition">Definition</TabsTrigger>
          <TabsTrigger value="parameters">Parameters</TabsTrigger>
          <TabsTrigger value="execution">Execution</TabsTrigger>
          <TabsTrigger value="advanced">Advanced</TabsTrigger>
        </TabsList>
      </Tabs>
      <fieldset disabled={busy !== null || locked} className="min-w-0">
        <FieldGroup>
          {section === "definition" && (
            <>
              <Field>
                <FieldLabel>Tool name</FieldLabel>
                <Input value={config.name} disabled className="font-mono" />
                <FieldDescription>
                  The tool name stays the same across versions. Create a draft
                  to change its configuration.
                </FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor={`tool-description-${version.id}`}>
                  Description
                </FieldLabel>
                <Textarea
                  id={`tool-description-${version.id}`}
                  value={config.description}
                  onChange={(event) =>
                    setField("description", event.target.value)
                  }
                  rows={3}
                />
                <FieldDescription>
                  The model receives this as the function description. Explain
                  when to use the tool; put overall conversation behavior in the
                  agent prompt and argument-specific guidance in the parameter
                  descriptions below.
                </FieldDescription>
              </Field>
            </>
          )}
          {section === "execution" && (
            <>
              <Field>
                <FieldLabel>Execution</FieldLabel>
                <Input
                  value={
                    config.kind === "registered"
                      ? "Registered backend handler"
                      : "HTTP request"
                  }
                  disabled
                />
              </Field>

              {config.kind === "registered" && (
                <>
                  <Field>
                    <FieldLabel htmlFor={`tool-handler-${version.id}`}>
                      Handler
                    </FieldLabel>
                    <NativeSelect
                      id={`tool-handler-${version.id}`}
                      value={config.handler ?? ""}
                      onChange={(event) => {
                        const handler = event.target.value || null;
                        setField("handler", handler);
                        if (handler !== "send_whatsapp_template")
                          setField("whatsapp", null);
                      }}
                    >
                      <NativeSelectOption value="">
                        Select reviewed handler
                      </NativeSelectOption>
                      {handlers.map((handler) => (
                        <NativeSelectOption
                          key={handler.name}
                          value={handler.name}
                        >
                          {handler.name}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                    <FieldDescription>
                      {selectedHandler?.description}
                    </FieldDescription>
                  </Field>
                  {config.handler === "send_whatsapp_template" &&
                    config.whatsapp && (
                      <WhatsAppDraftFields
                        versionId={version.id}
                        config={config.whatsapp}
                        mapping={whatsappMapping}
                        onMappingChange={setWhatsappMapping}
                        onChange={(whatsapp) => setField("whatsapp", whatsapp)}
                      />
                    )}
                </>
              )}

              {config.kind === "http" && config.http && (
                <>
                  <Field>
                    <FieldLabel htmlFor={`tool-url-${version.id}`}>
                      Endpoint
                    </FieldLabel>
                    <Input
                      id={`tool-url-${version.id}`}
                      value={config.http.url}
                      onChange={(event) =>
                        setHttpField("url", event.target.value)
                      }
                    />
                  </Field>
                  <div className="grid gap-4 md:grid-cols-2">
                    <Field>
                      <FieldLabel htmlFor={`tool-method-${version.id}`}>
                        Method
                      </FieldLabel>
                      <NativeSelect
                        id={`tool-method-${version.id}`}
                        value={config.http.method}
                        onChange={(event) =>
                          setHttpField("method", event.target.value)
                        }
                      >
                        {(
                          ["GET", "POST", "PUT", "PATCH", "DELETE"] as const
                        ).map((method) => (
                          <NativeSelectOption key={method} value={method}>
                            {method}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor={`tool-timeout-${version.id}`}>
                        Timeout (seconds)
                      </FieldLabel>
                      <Input
                        id={`tool-timeout-${version.id}`}
                        type="number"
                        min={1}
                        max={120}
                        value={config.http.timeout_secs}
                        onChange={(event) =>
                          setHttpField(
                            "timeout_secs",
                            Number(event.target.value),
                          )
                        }
                      />
                    </Field>
                  </div>
                  <Field>
                    <FieldLabel htmlFor={`tool-secret-${version.id}`}>
                      Secret reference
                    </FieldLabel>
                    <Input
                      id={`tool-secret-${version.id}`}
                      value={config.http.secret_reference ?? ""}
                      onChange={(event) =>
                        setHttpField(
                          "secret_reference",
                          event.target.value || null,
                        )
                      }
                      placeholder="integration-secret-id"
                    />
                  </Field>
                  <div className="grid gap-4 md:grid-cols-2">
                    <Field>
                      <FieldLabel htmlFor={`tool-mapping-${version.id}`}>
                        Argument mapping
                      </FieldLabel>
                      <Textarea
                        id={`tool-mapping-${version.id}`}
                        value={mapping}
                        onChange={(event) => setMapping(event.target.value)}
                        placeholder="caller_name -> customer_name"
                        rows={4}
                      />
                      <FieldDescription>
                        One mapping per line: tool argument -&gt; request field.
                      </FieldDescription>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor={`tool-extraction-${version.id}`}>
                        Output extraction
                      </FieldLabel>
                      <Textarea
                        id={`tool-extraction-${version.id}`}
                        value={extraction}
                        onChange={(event) => setExtraction(event.target.value)}
                        placeholder="status -> data.status"
                        rows={4}
                      />
                      <FieldDescription>
                        One mapping per line: result field -&gt; response path.
                      </FieldDescription>
                    </Field>
                  </div>
                </>
              )}
            </>
          )}
          {section === "parameters" && (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium">Input parameters</h3>
                  <p className="text-xs text-muted-foreground">
                    Names, descriptions, and required status become the
                    function-calling schema. For WhatsApp templates, describe
                    what each placeholder should contain.
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setRows((current) => [
                      ...current,
                      {
                        name: "",
                        type: "string",
                        description: "",
                        required: false,
                      },
                    ])
                  }
                >
                  Add parameter
                </Button>
              </div>
              <div className="flex flex-col gap-3">
                {rows.map((row, index) => (
                  <div
                    key={`${version.id}-${index}`}
                    className="grid gap-2 rounded-md border p-3 md:grid-cols-[1fr_120px_1.5fr_auto]"
                  >
                    <Input
                      value={row.name}
                      placeholder="parameter_name"
                      onChange={(event) =>
                        setRows((current) =>
                          current.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, name: event.target.value }
                              : item,
                          ),
                        )
                      }
                    />
                    <NativeSelect
                      value={row.type}
                      onChange={(event) =>
                        setRows((current) =>
                          current.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, type: event.target.value }
                              : item,
                          ),
                        )
                      }
                    >
                      {!["string", "number", "integer", "boolean"].includes(
                        row.type,
                      ) && (
                        <NativeSelectOption value={row.type}>
                          {row.type || "Schema reference"}
                        </NativeSelectOption>
                      )}
                      {(
                        ["string", "number", "integer", "boolean"] as const
                      ).map((type) => (
                        <NativeSelectOption key={type} value={type}>
                          {type}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                    <Input
                      value={row.description}
                      placeholder="Description"
                      onChange={(event) =>
                        setRows((current) =>
                          current.map((item, itemIndex) =>
                            itemIndex === index
                              ? { ...item, description: event.target.value }
                              : item,
                          ),
                        )
                      }
                    />
                    <div className="flex items-center gap-2 text-xs">
                      <label className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          checked={row.required}
                          onChange={(event) =>
                            setRows((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index
                                  ? { ...item, required: event.target.checked }
                                  : item,
                              ),
                            )
                          }
                        />
                        Required
                      </label>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setRows((current) =>
                            current.filter(
                              (_, itemIndex) => itemIndex !== index,
                            ),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {section === "advanced" && (
            <Field>
              <FieldLabel htmlFor="tool-schema">Input JSON schema</FieldLabel>
              <Textarea
                id="tool-schema"
                className="font-mono"
                rows={18}
                value={schemaText}
                onChange={(event) => {
                  setSchemaText(event.target.value);
                  setSchemaEdited(true);
                }}
              />
              <FieldDescription>
                Edit nested objects, arrays, enums, and schema constraints.
                These are retained by the structured editor.
              </FieldDescription>
            </Field>
          )}
        </FieldGroup>
      </fieldset>

      <Dialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && !busy && blocker.state === "blocked") blocker.reset();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Unsaved changes</DialogTitle>
            <DialogDescription>
              Save this draft before leaving, or discard your unsaved changes.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={busy !== null}
              onClick={() => blocker.state === "blocked" && blocker.reset()}
            >
              Stay
            </Button>
            <Button
              variant="outline"
              disabled={busy !== null}
              onClick={() => blocker.state === "blocked" && blocker.proceed()}
            >
              Discard changes
            </Button>
            <Button
              disabled={busy !== null || conflict || locked}
              onClick={() => {
                void save().then((ok) => {
                  if (ok && blocker.state === "blocked") blocker.proceed();
                });
              }}
            >
              Save & leave
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={reloadOpen} onOpenChange={setReloadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Stored revision {version.revision}</DialogTitle>
            <DialogDescription>
              Your current edits remain in the editor until you choose to
              reload.
            </DialogDescription>
          </DialogHeader>
          <pre className="max-h-72 overflow-auto text-xs">
            {JSON.stringify(version.config, null, 2)}
          </pre>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReloadOpen(false)}>
              Keep edits
            </Button>
            <Button
              onClick={() => {
                adopt(version);
                setReloadOpen(false);
              }}
            >
              Discard edits & reload
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function WhatsAppDraftFields({
  versionId,
  config,
  mapping,
  onMappingChange,
  onChange,
}: {
  versionId: string;
  config: WhatsAppConfig;
  mapping: string;
  onMappingChange: (value: string) => void;
  onChange: (value: WhatsAppConfig) => void;
}) {
  return (
    <div className="flex flex-col gap-4 rounded-md border p-3">
      <div>
        <h3 className="text-sm font-medium">WhatsApp template</h3>
        <p className="text-xs text-muted-foreground">
          {config.template_name} · {config.language}. Template copy is approved
          and owned by Meta; this tool supplies its variable values and optional
          header media.
        </p>
      </div>
      <Field>
        <FieldLabel>Image header</FieldLabel>
        <Suspense fallback={<p role="status">Loading media picker…</p>}>
          <WhatsAppMediaPicker
            connectionId={config.connection_id}
            selectedProviderId={
              config.header?.format === "IMAGE" ? config.header.media_id : null
            }
            onSelect={(mediaId) =>
              onChange({
                ...config,
                header: mediaId ? { format: "IMAGE", media_id: mediaId } : null,
              })
            }
          />
        </Suspense>
        <FieldDescription>
          The draft stores the Meta media ID directly. Only the local catalog
          UUID is used to request an authenticated preview.
        </FieldDescription>
      </Field>
      <Field>
        <FieldLabel htmlFor={`whatsapp-mappings-${versionId}`}>
          Template placeholder mapping
        </FieldLabel>
        <Textarea
          id={`whatsapp-mappings-${versionId}`}
          value={mapping}
          onChange={(event) => onMappingChange(event.target.value)}
          placeholder={"1 -> caller_name\n2 -> param_2"}
          rows={3}
        />
        <FieldDescription>
          One mapping per line: template placeholder number -&gt; tool argument.
          These arguments and their descriptions are passed to the model as the
          callable tool schema.
        </FieldDescription>
      </Field>
    </div>
  );
}
