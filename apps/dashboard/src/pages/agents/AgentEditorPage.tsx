import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, Settings2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { ApiError, useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import {
  LoadState,
  PageBody,
  ReadOnlyValue,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useResource } from "@/lib/resources";
import { ChatTestPanel } from "./ChatTestPanel";
import { AudioPanel } from "./AudioPanel";
import { CallbackSchedulingPanel } from "./CallbackSchedulingPanel";
import { ClassifierPanel } from "./ClassifierPanel";
import { ComposerPanel } from "./ComposerPanel";
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
  "Flow",
  "Chat test",
  "Prompts",
  "Models",
  "Audio",
  "Classifier",
  "Composer",
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
  const { canManage } = useOrganizationAccess();
  const resource = useResource<AgentVersion>(
    `/agent-versions/${versionId}`,
    Boolean(versionId),
  );
  const providers = useResource<ProviderCatalog>("/providers");
  const tools = useResource<{ tools: ToolSummary[] }>("/tools");
  const variables = useResource<ContactVariablesResponse>(
    "/contacts/variables",
  );
  const stored = resource.data;
  const initializedVersion = useRef<string | null>(null);
  const baseVersion = useRef<AgentVersion | null>(null);
  const [draft, setDraft] = useState<AgentConfig | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveDiagnostic, setSaveDiagnostic] =
    useState<ApiError["diagnostic"]>();
  const section =
    sections.find((item) => item.toLowerCase() === params.get("section")) ??
    "Flow";

  useEffect(() => {
    if (!stored) return;
    if (initializedVersion.current !== stored.id) {
      initializedVersion.current = stored.id;
      baseVersion.current = stored;
      setDraft(stored.config);
      setNote(stored.note ?? "");
      setConflict(false);
    } else if (baseVersion.current?.revision !== stored.revision) {
      setConflict(true);
    }
  }, [stored]);
  const dirty = Boolean(
    stored &&
    draft &&
    (JSON.stringify(draft) !== JSON.stringify(baseVersion.current?.config) ||
      note !== (baseVersion.current?.note ?? "")),
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

  const boundKeys = Object.keys(draft?.tool_bindings ?? {});
  const unboundToolReferences: string[] = [];
  if (draft) {
    draft.background_hooks?.forEach((h) => {
      if (!boundKeys.includes(h) && !unboundToolReferences.includes(h))
        unboundToolReferences.push(h);
    });
    draft.flow?.nodes?.forEach((node) => {
      node.tool_bindings?.forEach((t) => {
        if (!boundKeys.includes(t) && !unboundToolReferences.includes(t))
          unboundToolReferences.push(t);
      });
      node.entry_actions?.forEach((t) => {
        if (!boundKeys.includes(t) && !unboundToolReferences.includes(t))
          unboundToolReferences.push(t);
      });
      node.exit_actions?.forEach((t) => {
        if (!boundKeys.includes(t) && !unboundToolReferences.includes(t))
          unboundToolReferences.push(t);
      });
    });
  }

  function cleanUnboundReferences() {
    if (!draft) return;
    const bound = Object.keys(draft.tool_bindings);
    setDraft({
      ...draft,
      background_hooks: (draft.background_hooks ?? []).filter((h) =>
        bound.includes(h),
      ),
      flow: {
        ...draft.flow,
        nodes: draft.flow.nodes.map((n) => ({
          ...n,
          tool_bindings: n.tool_bindings.filter((t) => bound.includes(t)),
          entry_actions: n.entry_actions.filter((t) => bound.includes(t)),
          exit_actions: n.exit_actions.filter((t) => bound.includes(t)),
        })),
      },
    });
    toast.success("Removed unbound tool references from flow nodes");
  }

  async function save() {
    if (!stored || !draft || stored.status !== "draft" || conflict) return;
    if (unboundToolReferences.length > 0) {
      toast.error(
        `Cannot save draft: flow references unbound tools [${unboundToolReferences.join(", ")}]. Remove them or bind them in Tools first.`,
      );
      return;
    }
    setBusy(true);
    setSaveError(null);
    setSaveDiagnostic(undefined);
    try {
      await api(`/agent-versions/${stored.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          revision: baseVersion.current?.revision,
          config: draft,
          note: note || null,
        }),
      });
      toast.success("Draft saved");
      initializedVersion.current = null;
      await resource.reload();
    } catch (cause) {
      setSaveDiagnostic(
        cause instanceof ApiError ? cause.diagnostic : undefined,
      );
      setSaveError(
        cause instanceof Error ? cause.message : "Could not save draft",
      );
      if (cause instanceof Error && /changed|409/i.test(cause.message))
        setConflict(true);
      toast.error(
        cause instanceof Error ? cause.message : "Could not save draft",
      );
    } finally {
      setBusy(false);
    }
  }

  const disabled = stored?.status !== "draft" || !canManage;
  const registeredTools = tools.data?.tools.map((tool) => tool.name) ?? [];
  return (
    <PageBody wide>
      <header className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h1 className="truncate text-lg font-semibold">
            {draft?.name ?? "Agent version"}
          </h1>
          {stored && <StatusBadge value={stored.status} />}
          {stored && (
            <span className="text-xs text-muted-foreground">
              v{stored.version} · Revision {stored.revision}
              {disabled ? " · Read only" : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {stored && (
            <span className="text-xs text-muted-foreground" role="status">
              {busy
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : "All changes saved"}
            </span>
          )}
          {!disabled && (
            <Button
              disabled={busy || !dirty || conflict}
              onClick={() => void save()}
            >
              {busy ? "Saving…" : "Save changes"}
            </Button>
          )}
          <Button asChild variant="outline" size="sm">
            <Link to={`/agents/${agentId}`}>Versions</Link>
          </Button>
        </div>
      </header>
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
            {saveError && (
              <p role="alert" className="text-sm text-destructive">
                Save failed: {saveError}
              </p>
            )}
            {saveError && saveDiagnostic?.diagnostic_id && (
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>Stage: {saveDiagnostic.stage ?? "save"}</span>
                {saveDiagnostic.timestamp && (
                  <time dateTime={saveDiagnostic.timestamp}>
                    {new Date(saveDiagnostic.timestamp).toLocaleString()}
                  </time>
                )}
                <code>Diagnostic ID: {saveDiagnostic.diagnostic_id}</code>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    if (!navigator.clipboard) {
                      toast.error("Copy the displayed diagnostic ID manually");
                      return;
                    }
                    void navigator.clipboard
                      .writeText(saveDiagnostic.diagnostic_id!)
                      .catch(() => toast.error("Could not copy diagnostic ID"));
                  }}
                >
                  Copy diagnostic ID
                </Button>
              </div>
            )}
            {providers.error && (
              <p className="text-sm text-destructive">
                Provider catalog unavailable: {providers.error}. Stored values
                remain visible.
              </p>
            )}
            {unboundToolReferences.length > 0 && !disabled && (
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm">
                <div>
                  <strong className="text-destructive">
                    Unbound tool references detected:
                  </strong>{" "}
                  <span className="font-mono text-xs">
                    {unboundToolReferences.join(", ")}
                  </span>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    These tools are assigned to flow nodes or hooks but not
                    bound under Tools. Saving will fail until resolved.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={cleanUnboundReferences}
                  className="border-destructive/40 text-destructive hover:bg-destructive/20"
                >
                  Clean unbound references
                </Button>
              </div>
            )}
            <nav
              aria-label="Version configuration"
              className="flex flex-wrap gap-1 bg-transparent px-2 py-1"
            >
              {sections
                .filter((item) =>
                  [
                    "Flow",
                    "Chat test",
                    "Prompts",
                    "Tools",
                    "Knowledge",
                  ].includes(item),
                )
                .map((item) => (
                  <Button
                    key={item}
                    type="button"
                    size="sm"
                    variant="tab"
                    aria-current={section === item ? "page" : undefined}
                    onClick={() => setParams({ section: item.toLowerCase() })}
                  >
                    {item === "Prompts" ? "Global prompt" : item}
                  </Button>
                ))}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    size="sm"
                    variant="tab"
                    aria-current={
                      [
                        "Models",
                        "Audio",
                        "Classifier",
                        "Composer",
                        "Context",
                        "Logging",
                        "Callback Scheduling",
                      ].includes(section)
                        ? "page"
                        : undefined
                    }
                  >
                    <Settings2 data-icon="inline-start" />
                    {[
                      "Models",
                      "Audio",
                      "Classifier",
                      "Composer",
                      "Context",
                      "Logging",
                      "Callback Scheduling",
                    ].includes(section)
                      ? `Settings: ${section}`
                      : "Settings"}
                    <ChevronDown data-icon="inline-end" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuGroup>
                    {sections
                      .filter(
                        (item) =>
                          ![
                            "Flow",
                            "Chat test",
                            "Prompts",
                            "Tools",
                            "Knowledge",
                          ].includes(item),
                      )
                      .map((item) => (
                        <DropdownMenuItem
                          key={item}
                          onSelect={() =>
                            setParams({ section: item.toLowerCase() })
                          }
                        >
                          {item}
                        </DropdownMenuItem>
                      ))}
                  </DropdownMenuGroup>
                </DropdownMenuContent>
              </DropdownMenu>
            </nav>
            {section === "Chat test" && stored && (
              <ChatTestPanel
                key={stored.id}
                version={stored}
                dirty={dirty}
                save={save}
              />
            )}
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
                classifierContract={providers.data?.classifier_contract}
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
            {section === "Composer" && (
              <ComposerPanel
                config={draft}
                change={setDraft}
                catalog={providers.data}
                disabled={disabled}
              />
            )}
            {section === "Context" && (
              <ContextPanel
                config={draft}
                change={setDraft}
                catalog={providers.data}
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
              <CallbackSchedulingPanel
                config={draft}
                change={setDraft}
                disabled={disabled}
              />
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
