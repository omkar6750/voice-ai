import { useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import { useResource } from "@/lib/resources";

type ToolVersion = {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  config: {
    name: string;
    description: string;
    kind: string;
    handler?: string | null;
    http?: { url: string; method: string } | null;
    parameters?: Record<string, unknown> | null;
    wait?: { mode: string; acknowledgement?: string | null } | null;
  };
};

export function ToolDetailPage() {
  const { toolId = "" } = useParams();
  const api = useApi();
  const { data, loading, error, reload } = useResource<{
    versions: ToolVersion[];
  }>(`/tools/${toolId}/versions`);
  const [busy, setBusy] = useState<string | null>(null);
  async function action(version: ToolVersion, kind: "clone" | "publish") {
    setBusy(version.id);
    try {
      await api(`/tool-versions/${version.id}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ revision: version.revision }),
      });
      toast.success(kind === "clone" ? "Draft cloned" : "Tool published");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed");
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
              <ReadOnlyValue
                label="Handler"
                value={version.config.handler || "Not applicable"}
              />
              <ReadOnlyValue
                label="Endpoint"
                value={version.config.http?.url || "Not applicable"}
              />
              <ReadOnlyValue
                label="Method"
                value={version.config.http?.method || "Not applicable"}
              />
              <ReadOnlyValue
                label="Wait mode"
                value={version.config.wait?.mode || "inline"}
              />
              {version.config.wait?.acknowledgement && (
                <ReadOnlyValue
                  label="Wait acknowledgement"
                  value={version.config.wait.acknowledgement}
                />
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
                    disabled={busy === version.id}
                    onClick={() => void action(version, "publish")}
                  >
                    Publish
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy === version.id}
                    onClick={() => void action(version, "clone")}
                  >
                    Clone draft
                  </Button>
                )}
              </div>
            </section>
          ))}
        </div>
      </LoadState>
      <p className="text-xs text-muted-foreground">
        Tool draft field editor remains pending handler capabilities and
        validated HTTP destination controls. Versions are never edited through a
        raw JSON form.
      </p>
    </PageBody>
  );
}
