import { useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import type { components } from "@/generated/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CopyId, useToolResource } from "./workspace";
import { PublishDialog } from "./PublishDialog";

type Page = components["schemas"]["ToolVersionPage"];
type Version = components["schemas"]["ToolVersionSummary"];
type Usage = components["schemas"]["ToolUsagePage"];

export function ToolDetailPage() {
  const { toolId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = ["draft", "published", "usage"].includes(params.get("tab") ?? "")
    ? params.get("tab")!
    : "draft";
  const before = params.get("before");
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const navigate = useNavigate();
  const api = useApi();
  const { canManage } = useOrganizationAccess();
  const page = useToolResource<Page>(
    "/tools/" +
      toolId +
      "/versions?view=summary&status=" +
      (tab === "usage" ? "draft" : tab) +
      "&limit=20" +
      (before && tab !== "usage" ? "&before_version=" + before : ""),
  );
  const usage = useToolResource<Usage>(
    "/tools/" + toolId + "/usage?offset=" + offset + "&limit=20",
    tab === "usage",
  );
  const from = params.get("from");
  const [source, setSource] = useState<Pick<
    Version,
    "id" | "version" | "revision"
  > | null>(null);
  const [createOpen, setCreateOpen] = useState(Boolean(from));
  const [creating, setCreating] = useState(false);
  const cloning = useRef(false);
  const [candidate, setCandidate] = useState<Version | null>(null);
  const fromVersion = useToolResource<
    components["schemas"]["ToolVersionResponse"]
  >(
    "/tool-versions/" + (from ?? "") + "?tool_id=" + toolId,
    createOpen && Boolean(from) && !source,
  );
  const latest = useToolResource<Page>(
    "/tools/" + toolId + "/versions?view=summary&status=published&limit=1",
    createOpen && !source && !from,
  );
  const drafts = useToolResource<Page>(
    "/tools/" + toolId + "/versions?view=summary&status=draft&limit=5",
    createOpen,
  );
  const cloneSource =
    source ?? (from ? fromVersion.data : latest.data?.versions[0]);
  async function clone() {
    if (!cloneSource || cloning.current) return;
    cloning.current = true;
    setCreating(true);
    try {
      const result = await api<
        components["schemas"]["ToolVersionMutationResponse"]
      >("/tool-versions/" + cloneSource.id + "/clone", {
        method: "POST",
        body: JSON.stringify({ revision: cloneSource.revision }),
      });
      await page.invalidate();
      toast.success("Draft created");
      navigate("/tools/" + toolId + "/versions/" + result.id + "/edit");
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not create draft",
      );
    } finally {
      cloning.current = false;
      setCreating(false);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title={page.data?.tool_name ?? "Tool"}
        description="Manage drafts, published versions, and agent bindings."
        action={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link to="/tools">All tools</Link>
            </Button>
            {canManage && (
              <Button
                onClick={() => {
                  setSource(null);
                  const next = new URLSearchParams(params);
                  next.delete("from");
                  setParams(next, { replace: true });
                  setCreateOpen(true);
                }}
              >
                Create draft
              </Button>
            )}
          </div>
        }
        readOnlyAction={
          <Button asChild variant="outline">
            <Link to="/tools">All tools</Link>
          </Button>
        }
      />
      <CopyId label="Tool ID" value={toolId} />
      <Tabs value={tab} onValueChange={(next) => setParams({ tab: next })}>
        <TabsList variant="line">
          <TabsTrigger value="draft">Drafts</TabsTrigger>
          <TabsTrigger value="published">Published versions</TabsTrigger>
          <TabsTrigger value="usage">Used by agents</TabsTrigger>
        </TabsList>
      </Tabs>
      {tab === "usage" ? (
        <LoadState
          loading={usage.isPending}
          error={usage.error?.message ?? null}
          empty={
            usage.data?.bindings.length === 0
              ? "No agent versions pin this tool."
              : undefined
          }
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agent</TableHead>
                  <TableHead>Binding</TableHead>
                  <TableHead>Pinned tool version</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usage.data?.bindings.map((row) => (
                  <TableRow key={row.agent_version_id + ":" + row.binding_key}>
                    <TableCell>
                      <Link
                        className="font-medium text-primary hover:underline"
                        to={
                          "/agents/" +
                          row.agent_id +
                          "/versions/" +
                          row.agent_version_id
                        }
                      >
                        {row.agent_name} · v{row.agent_version}
                      </Link>
                      <div>
                        <StatusBadge value={row.agent_status} />
                      </div>
                      <div>
                        <CopyId label="Agent ID" value={row.agent_id} />
                      </div>
                      <div>
                        <CopyId
                          label="Agent Version ID"
                          value={row.agent_version_id}
                        />
                      </div>
                    </TableCell>
                    <TableCell>
                      <code>{row.binding_key}</code>
                    </TableCell>
                    <TableCell>
                      <Link
                        to={
                          "/tools/" +
                          toolId +
                          "/versions/" +
                          row.tool_version_id
                        }
                      >
                        v{row.tool_version}
                      </Link>
                      <div>
                        <CopyId label="Tool ID" value={row.tool_id} />
                      </div>
                      <div>
                        <CopyId
                          label="Tool Version ID"
                          value={row.tool_version_id}
                        />
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <nav aria-label="Agent usage pages" className="flex justify-between">
            <Button
              variant="outline"
              disabled={!offset || usage.isFetching}
              onClick={() =>
                setParams({ tab, offset: String(Math.max(0, offset - 20)) })
              }
            >
              Previous
            </Button>
            <Button
              variant="outline"
              disabled={!usage.data?.has_more || usage.isFetching}
              onClick={() => setParams({ tab, offset: String(offset + 20) })}
            >
              Next
            </Button>
          </nav>
        </LoadState>
      ) : (
        <LoadState
          loading={page.isPending}
          error={page.error?.message ?? null}
          empty={
            page.data?.versions.length === 0
              ? "No " +
                (tab === "draft" ? "drafts" : "published versions") +
                " on this page."
              : undefined
          }
        >
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Based on</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.data?.versions.map((version) => (
                  <TableRow key={version.id}>
                    <TableCell>
                      <Link
                        className="font-medium text-primary hover:underline"
                        to={"/tools/" + toolId + "/versions/" + version.id}
                      >
                        v{version.version}
                      </Link>
                      <div>
                        <CopyId label="Version ID" value={version.id} />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        Revision {version.revision}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge value={version.status} />
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {new Date(version.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      {version.parent_version
                        ? "v" + version.parent_version
                        : "Original"}
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-2">
                        {version.status === "draft" ? (
                          <>
                            {canManage && (
                              <>
                                <Button asChild size="sm">
                                  <Link
                                    to={
                                      "/tools/" +
                                      toolId +
                                      "/versions/" +
                                      version.id +
                                      "/edit"
                                    }
                                  >
                                    Edit draft
                                  </Link>
                                </Button>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setCandidate(version)}
                                >
                                  Publish…
                                </Button>
                              </>
                            )}
                          </>
                        ) : (
                          <>
                            <Button asChild variant="outline" size="sm">
                              <Link
                                to={
                                  "/tools/" + toolId + "/versions/" + version.id
                                }
                              >
                                View
                              </Link>
                            </Button>
                            {canManage && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setSource(version);
                                  setCreateOpen(true);
                                }}
                              >
                                Create draft
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </LoadState>
      )}
      {tab !== "usage" && (
        <nav aria-label="Version pages" className="flex justify-between">
          <Button
            variant="outline"
            disabled={!before || page.isFetching}
            onClick={() => setParams({ tab })}
          >
            Newest
          </Button>
          <Button
            variant="outline"
            disabled={!page.data?.has_more || page.isFetching}
            onClick={() =>
              setParams({ tab, before: String(page.data!.next_before_version) })
            }
          >
            Older versions
          </Button>
        </nav>
      )}
      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          if (!creating) setCreateOpen(open);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Create draft{cloneSource ? " from v" + cloneSource.version : ""}
            </DialogTitle>
            <DialogDescription>
              The new version belongs to this tool. Published versions and agent
              bindings stay unchanged.
            </DialogDescription>
          </DialogHeader>
          <LoadState
            loading={
              drafts.isPending ||
              (!source && (from ? fromVersion.isPending : latest.isPending))
            }
            error={
              drafts.error?.message ??
              (from ? fromVersion.error?.message : latest.error?.message) ??
              null
            }
          >
            {drafts.data?.versions.length ? (
              <div className="flex flex-col gap-2">
                <p className="text-sm">Continue an existing draft:</p>
                {drafts.data.versions.map((draft) => (
                  <Button key={draft.id} asChild variant="outline">
                    <Link
                      to={
                        "/tools/" + toolId + "/versions/" + draft.id + "/edit"
                      }
                    >
                      Open draft v{draft.version} · revision {draft.revision}
                    </Link>
                  </Button>
                ))}
              </div>
            ) : null}
            {!cloneSource && (
              <p className="text-sm text-muted-foreground">
                No published version is available. Open an existing draft to
                continue editing.
              </p>
            )}
          </LoadState>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={creating}
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button
              disabled={
                creating ||
                !cloneSource ||
                (!source && (from ? fromVersion.isError : latest.isError)) ||
                drafts.isError
              }
              onClick={() => void clone()}
            >
              {creating
                ? "Creating…"
                : drafts.data?.versions.length
                  ? "Create another draft"
                  : "Create draft"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PublishDialog
        candidate={candidate}
        close={() => setCandidate(null)}
        onPublished={async () => {
          const id = candidate?.id;
          await page.invalidate();
          if (id) navigate("/tools/" + toolId + "/versions/" + id);
        }}
      />
    </PageBody>
  );
}
