import { lazy, Suspense, useCallback, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useOrganizationAccess } from "@/app/access";
import type { components } from "@/generated/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CopyId, useToolResource } from "./workspace";
import { PublishDialog } from "./PublishDialog";

const ToolEditor = lazy(() =>
  import("./ToolEditor").then((module) => ({ default: module.ToolEditor })),
);
type Version = components["schemas"]["ToolVersionResponse"];
type Handlers = components["schemas"]["ToolHandlerCatalog"];

export function ToolVersionPage() {
  const { toolId = "", versionId = "" } = useParams();
  const { canManage } = useOrganizationAccess();
  const location = useLocation();
  const navigate = useNavigate();
  const editing = location.pathname.endsWith("/edit");
  const resource = useToolResource<Version>(
    "/tool-versions/" + versionId + "?tool_id=" + toolId,
  );
  const [section, setSection] = useState("definition");
  const [hasUnsavedEdits, setHasUnsavedEdits] = useState(false);
  const onSectionChange = useCallback((value: string) => setSection(value), []);
  const handlers = useToolResource<Handlers>(
    "/tools/handlers",
    editing && section === "execution",
  );
  const [candidate, setCandidate] = useState<Version | null>(null);
  const version = resource.data;
  const base = "/tools/" + toolId + "/versions/" + versionId;
  return (
    <PageBody>
      <PageHeader
        title={
          version
            ? version.config.name + " · v" + version.version
            : "Tool version"
        }
        description={
          editing
            ? "Edit this draft. Save changes before reviewing publication."
            : "Inspect the exact configuration and version identifiers."
        }
        action={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link to={"/tools/" + toolId}>Version history</Link>
            </Button>
            {version?.status === "draft" &&
              (editing ? (
                <Button asChild variant="outline">
                  <Link to={base}>Review saved version</Link>
                </Button>
              ) : (
                <>
                  <Button asChild>
                    <Link to={base + "/edit"}>Edit draft</Link>
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setCandidate(version)}
                  >
                    Publish…
                  </Button>
                </>
              ))}
            {version?.status === "published" && (
              <Button asChild>
                <Link
                  to={"/tools/" + toolId + "?tab=published&from=" + version.id}
                >
                  Create draft…
                </Link>
              </Button>
            )}
          </div>
        }
        readOnlyAction={
          <Button asChild variant="outline">
            <Link to={"/tools/" + toolId}>Version history</Link>
          </Button>
        }
      />
      <div className="flex flex-wrap gap-x-6 gap-y-2">
        <CopyId label="Tool ID" value={toolId} />
        <CopyId label="Version ID" value={versionId} />
        {version && <StatusBadge value={version.status} />}
      </div>
      <LoadState
        loading={resource.isPending}
        error={!version ? (resource.error?.message ?? null) : null}
      >
        {version && resource.error && (
          <Alert variant="destructive">
            <AlertTitle>Could not refresh version</AlertTitle>
            <AlertDescription>
              {resource.error.message}. Your current editor remains open.
            </AlertDescription>
          </Alert>
        )}
        {version &&
          (editing &&
          canManage &&
          (version.status === "draft" || hasUnsavedEdits) ? (
            <Suspense fallback={<Skeleton className="h-64 w-full" />}>
              <ToolEditor
                key={version.id}
                version={version}
                onDirtyChange={setHasUnsavedEdits}
                handlers={handlers.data?.handlers ?? []}
                onSectionChange={onSectionChange}
                onSaved={(next) => {
                  resource.setData(next);
                  void resource.invalidate();
                }}
                onConflict={() => {
                  void resource.refetch();
                }}
              />
              {section === "execution" && handlers.error && (
                <p role="alert">{handlers.error.message}</p>
              )}
            </Suspense>
          ) : (
            <section className="flex flex-col gap-6">
              <ReadOnlyValue label="Revision" value={version.revision} />
              <ReadOnlyValue
                label="Description"
                value={version.config.description || "No description"}
              />
              <ReadOnlyValue
                label="Execution"
                value={
                  version.config.kind === "http"
                    ? "HTTP request"
                    : "Registered backend handler"
                }
              />
              <ReadOnlyValue
                label="Handler / endpoint"
                value={
                  version.config.handler ??
                  version.config.http?.url ??
                  "Unconfigured"
                }
              />
              <details>
                <summary className="cursor-pointer text-sm font-medium">
                  Input schema
                </summary>
                <pre className="mt-3 overflow-auto text-xs">
                  {JSON.stringify(version.config.parameters, null, 2)}
                </pre>
              </details>
              <details>
                <summary className="cursor-pointer text-sm font-medium">
                  Complete configuration
                </summary>
                <pre className="mt-3 overflow-auto text-xs">
                  {JSON.stringify(version.config, null, 2)}
                </pre>
              </details>
              <p className="text-xs text-muted-foreground">
                {version.status === "published"
                  ? "This published version is immutable. Create a draft to change it."
                  : "Publishing makes this saved configuration immutable. Agents keep their existing version bindings."}
              </p>
            </section>
          ))}
      </LoadState>
      <PublishDialog
        candidate={candidate}
        close={() => setCandidate(null)}
        onPublished={async () => {
          await resource.invalidate();
          navigate(base);
        }}
      />
    </PageBody>
  );
}
