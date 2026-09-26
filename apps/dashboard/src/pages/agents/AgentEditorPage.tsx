import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useResource } from "@/lib/resources";
import { AudioPanel } from "./AudioPanel";
import { CallbackSchedulingPanel } from "./CallbackSchedulingPanel";
import { ClassifierPanel } from "./ClassifierPanel";
import { ContextPanel } from "./ContextPanel";
import { FlowPanel } from "./FlowPanel";
import { KnowledgePanel } from "./KnowledgePanel";
import { ModelsPanel } from "./ModelsPanel";
import { PromptsPanel } from "./PromptsPanel";
import { ToolsPanel } from "./ToolsPanel";
import type {
  AgentConfig,
  AgentVersion,
  ContactVariablesResponse,
  ProviderCatalog,
  ToolSummary,
} from "./types";

const sections = [
  "Prompts",
  "Flow",
  "Models",
  "Audio",
  "Classifier",
  "Context",
  "Tools",
  "Knowledge",
  "Logging",
  "Callback Scheduling",
] as const;


export function AgentEditorPage() {
  const { agentId = "", versionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const api = useApi();
  const resource = useResource<{ versions: AgentVersion[] }>(
    `/agents/${agentId}/versions`,
  );
  const providers = useResource<ProviderCatalog>("/providers");
  const tools = useResource<{ tools: ToolSummary[] }>("/tools");
  const variables = useResource<ContactVariablesResponse>("/contacts/variables");
  const stored = resource.data?.versions.find((item) => item.id === versionId);
  const [draft, setDraft] = useState<AgentConfig | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const section =
    sections.find((item) => item.toLowerCase() === params.get("section")) ??
    "Prompts";

  useEffect(() => {
    if (stored) {
      setDraft(stored.config);
      setNote(stored.note ?? "");
      setConflict(false);
    }
  }, [stored]);
  const dirty = Boolean(
    stored &&
    draft &&
    (JSON.stringify(draft) !== JSON.stringify(stored.config) ||
      note !== (stored.note ?? "")),
  );
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function save() {
    if (!stored || !draft || stored.status !== "draft") return;
    setBusy(true);
    try {
      await api(`/agent-versions/${stored.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          revision: stored.revision,
          config: draft,
          note: note || null,
        }),
      });
      toast.success("Draft saved");
      await resource.reload();
    } catch (cause) {
      if (cause instanceof Error && /changed|409/i.test(cause.message))
        setConflict(true);
      toast.error(
        cause instanceof Error ? cause.message : "Could not save draft",
      );
    } finally {
      setBusy(false);
    }
  }

  const disabled = stored?.status !== "draft";
  const registeredTools = tools.data?.tools.map((tool) => tool.name) ?? [];
  return (
    <PageBody>
      <PageHeader
        title={draft ? `${draft.name} · v${stored?.version}` : "Agent version"}
        description={
          stored
            ? `Revision ${stored.revision}. Published versions cannot be edited.`
            : "Loading version"
        }
        action={
          <div className="flex items-center gap-2">
            {stored && <StatusBadge value={stored.status} />}
            {dirty && (
              <span className="text-xs text-muted-foreground">
                Unsaved changes
              </span>
            )}
            {!disabled && (
              <Button
                disabled={busy || !dirty || conflict}
                onClick={() => void save()}
              >
                {busy ? "Saving…" : "Save draft"}
              </Button>
            )}
            <Button asChild variant="outline">
              <Link to={`/agents/${agentId}`}>Versions</Link>
            </Button>
          </div>
        }
      />
      <LoadState
        loading={resource.loading}
        error={resource.error}
        empty={!stored ? "Version not found." : undefined}
      >
        {draft && stored && (
          <>
            {conflict && (
              <div
                role="alert"
                className="rounded-md border border-destructive p-3 text-sm text-destructive"
              >
                Draft changed elsewhere. Your edits remain here. Copy them
                before reloading, then reconcile manually. No overwrite
                attempted.
              </div>
            )}
            {providers.error && (
              <p className="text-sm text-destructive">
                Provider catalog unavailable: {providers.error}. Stored values
                remain visible.
              </p>
            )}
            <nav
              aria-label="Version configuration"
              className="flex flex-wrap gap-1 border-b pb-2"
            >
              {sections.map((item) => (
                <Button
                  key={item}
                  type="button"
                  size="sm"
                  variant={section === item ? "secondary" : "ghost"}
                  aria-current={section === item ? "page" : undefined}
                  onClick={() => setParams({ section: item.toLowerCase() })}
                >
                  {item}
                </Button>
              ))}
            </nav>
            {section === "Prompts" && (
              <PromptsPanel
                config={draft}
                change={setDraft}
                boundTools={Object.keys(draft.tool_bindings)}
                registeredTools={registeredTools}
                variablesCatalog={variables.data}
                disabled={disabled}
              />
            )}
            {section === "Flow" && (
              <FlowPanel
                config={draft}
                change={setDraft}
                registeredTools={registeredTools}
                variablesCatalog={variables.data}
                disabled={disabled}
              />
            )}
            {section === "Models" && (
              <ModelsPanel
                config={draft}
                change={setDraft}
                catalog={providers.data}
                disabled={disabled}
              />
            )}
            {section === "Audio" && (
              <AudioPanel
                config={draft}
                change={setDraft}
                disabled={disabled}
              />
            )}
            {section === "Classifier" && (
              <ClassifierPanel
                config={draft}
                change={setDraft}
                providers={providers.data}
                disabled={disabled}
              />
            )}
            {section === "Context" && (
              <ContextPanel
                config={draft}
                change={setDraft}
                disabled={disabled}
              />
            )}

            {section === "Tools" && (
              <ToolsPanel
                config={draft}
                change={setDraft}
                disabled={disabled}
              />
            )}
            {section === "Knowledge" && (
              <KnowledgePanel
                config={draft}
                change={setDraft}
                disabled={disabled}
              />
            )}
            {section === "Callback Scheduling" && (
              <CallbackSchedulingPanel config={draft} change={setDraft} disabled={disabled} />
            )}
            {section === "Logging" && (
              <section className="flex max-w-2xl flex-col gap-4">
                <h2 className="text-base font-semibold">Pipeline logs</h2>
                <Field>
                  <FieldLabel htmlFor="pipeline-logs">
                    Capture policy
                  </FieldLabel>
                  <NativeSelect
                    id="pipeline-logs"
                    value={draft.pipeline_logs}
                    disabled={disabled}
                    onChange={(event) =>
                      setDraft({
                        ...draft,
                        pipeline_logs: event.target
                          .value as AgentConfig["pipeline_logs"],
                      })
                    }
                  >
                    <option value="inherit">Inherit workspace</option>
                    <option value="enabled">Enabled</option>
                    <option value="disabled">Disabled</option>
                  </NativeSelect>
                </Field>
                <ReadOnlyValue
                  label="Agent name"
                  value={draft.name}
                  reason="Agent identity has no rename API. Name remains visible and unchanged."
                />
                <Field>
                  <FieldLabel htmlFor="version-note">Draft note</FieldLabel>
                  <Input
                    id="version-note"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    disabled={disabled}
                  />
                </Field>
              </section>
            )}
          </>
        )}
      </LoadState>
    </PageBody>
  );
}
