import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { useResource } from "@/lib/resources";
import { ToolEditor } from "./ToolEditor";

type ToolVersion = components["schemas"]["ToolVersionResponse"];
type HandlerCatalog = components["schemas"]["ToolHandlerCatalog"];

export function ToolDetailPage() {
  const { toolId = "" } = useParams();
  const api = useApi();
  const { data, loading, error, reload } = useResource<{
    versions: ToolVersion[];
  }>(`/tools/${toolId}/versions`);
  const { data: handlers } = useResource<HandlerCatalog>("/tools/handlers");
  const [busy, setBusy] = useState<string | null>(null);
  const [editingVersionId, setEditingVersionId] = useState<string | null>(null);
  async function clone(version: ToolVersion) {
    setBusy(version.id);
    try {
      await api(`/tool-versions/${version.id}/clone`, {
        method: "POST",
        body: JSON.stringify({ revision: version.revision }),
      });
      toast.success("Draft cloned");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not clone draft");
    } finally {
      setBusy(null);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title={data?.versions[0]?.config.name ?? "Tool"}
        description="Exact tool versions and their implementation settings."
        action={
          <Button asChild variant="outline">
            <Link to="/tools">All tools</Link>
          </Button>
        }
      />
      <LoadState
        loading={loading}
        error={error}
        empty={data?.versions.length === 0 ? "No versions found." : undefined}
      >
        <div className="grid gap-5 lg:grid-cols-2">
          {data?.versions.map((version) => (
            <section
              key={version.id}
              className="flex flex-col gap-3 border-b pb-5"
            >
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold">v{version.version}</h2>
                <StatusBadge value={version.status} />
              </div>
              <p className="text-sm text-muted-foreground">
                {version.config.description || "No description"}
              </p>
              <ReadOnlyValue label="Kind" value={version.config.kind} />
              {version.config.kind === "registered" ? (
                <>
                  <ReadOnlyValue label="Execution" value="Registered backend handler" />
                  <ReadOnlyValue label="Handler" value={version.config.handler ?? "Unconfigured"} />
                  <ReadOnlyValue
                    label="Provider"
                    value={version.config.whatsapp ? "WhatsApp Cloud API" : "Native runtime"}
                  />
                  {version.config.whatsapp && (
                    <ReadOnlyValue
                      label="WhatsApp template"
                      value={`${version.config.whatsapp.template_name} · ${version.config.whatsapp.language}`}
                    />
                  )}
                </>
              ) : (
                <>
                  <ReadOnlyValue label="Execution" value="HTTP request" />
                  <ReadOnlyValue label="Endpoint" value={version.config.http?.url ?? "Unconfigured"} />
                  <ReadOnlyValue label="Method" value={version.config.http?.method ?? "Unconfigured"} />
                </>
              )}
              <ReadOnlyValue
                label="Input schema"
                value={
                  version.config.parameters ? (
                    <code className="break-all text-xs">
                      {JSON.stringify(version.config.parameters)}
                    </code>
                  ) : (
                    "None"
                  )
                }
              />
              <div className="flex gap-2">
                {version.status === "draft" ? (
                  <Button
                    size="sm"
                    variant={editingVersionId === version.id ? "secondary" : "default"}
                    disabled={busy === version.id}
                    onClick={() => setEditingVersionId((current) => current === version.id ? null : version.id)}
                  >
                    {editingVersionId === version.id ? "Close editor" : "Edit draft"}
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy === version.id}
                    onClick={() => void clone(version)}
                  >
                    Clone draft
                  </Button>
                )}
              </div>
              {version.status === "draft" && editingVersionId === version.id && (
                <ToolEditor
                  version={version}
                  handlers={handlers?.handlers ?? []}
                  onSaved={async () => {
                    setEditingVersionId(null);
                    await reload();
                  }}
                />
              )}
            </section>
          ))}
        </div>
      </LoadState>
      <p className="text-xs text-muted-foreground">
        Published versions are immutable. Runtime execution timing comes from
        the registered handler; only lead classification continues in the
        background. Put caller-facing acknowledgement wording in the agent
        prompt or tool description.
      </p>
    </PageBody>
  );
}
