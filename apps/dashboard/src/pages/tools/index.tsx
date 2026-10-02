import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, Lock, MoreHorizontal, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import type { components } from "@/generated/api";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { CopyId, useToolResource } from "./workspace";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";

type Tool = components["schemas"]["ToolCatalogSummary"];
type ToolImpact = components["schemas"]["ToolImpactResponse"];

export function ToolsPage() {
  const api = useApi();
  const { canManage } = useOrganizationAccess();
  const resource = useToolResource<
    components["schemas"]["ToolCatalogResponse"]
  >("/tools?view=summary");
  const { data } = resource;
  const [params, setParams] = useSearchParams();
  const search = params.get("q") ?? "";
  const visible = data?.tools.filter((tool) =>
    (tool.name + " " + tool.id).toLowerCase().includes(search.toLowerCase()),
  );

  const [toolToDelete, setToolToDelete] = useState<Tool | null>(null);
  const [impact, setImpact] = useState<ToolImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function openDeleteModal(tool: Tool) {
    setToolToDelete(tool);
    setLoadingImpact(true);
    setImpact(null);
    try {
      const data = await api<ToolImpact>(`/tools/${tool.id}/impact`);
      setImpact(data);
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not inspect tool impact",
      );
    } finally {
      setLoadingImpact(false);
    }
  }

  async function confirmDelete() {
    if (!toolToDelete) return;
    setDeleting(true);
    try {
      await api(`/tools/${toolToDelete.id}`, {
        method: "DELETE",
      });
      toast.success(`Tool "${toolToDelete.name}" deleted`);
      setToolToDelete(null);
      await resource.invalidate();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not delete tool",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title="Tools"
        description="Published tool versions can be pinned to agent drafts. Node access is configured in each flow."
      />
      <Input
        aria-label="Search tools"
        placeholder="Search name or Tool ID"
        value={search}
        onChange={(event) => {
          const next = new URLSearchParams(params);
          if (event.target.value) next.set("q", event.target.value);
          else next.delete("q");
          setParams(next, { replace: true });
        }}
      />
      <LoadState
        loading={resource.isPending}
        error={resource.error?.message ?? null}
        empty={
          visible?.length === 0
            ? search
              ? "No matching tools."
              : "No tools registered yet."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tool</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Latest published</TableHead>
              <TableHead>Drafts</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible?.map((tool) => {
              const isSystemTool =
                tool.name === "change_node" || tool.name === "end_call";
              return (
                <TableRow key={tool.id}>
                  <TableCell className="font-medium">
                    <Link
                      className="font-mono text-sm text-primary hover:underline"
                      to={`/tools/${tool.id}`}
                    >
                      {tool.name}
                    </Link>
                    <div>
                      <CopyId label="Tool ID" value={tool.id} />
                    </div>
                  </TableCell>
                  <TableCell>
                    {isSystemTool ? (
                      <Badge
                        variant="secondary"
                        className="gap-1 font-normal text-xs"
                      >
                        <Lock className="size-3 text-muted-foreground" />
                        Core System Tool
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs font-normal">
                        Registered Tool
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {tool.latest_published_version
                      ? "v" + tool.latest_published_version
                      : "None"}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {tool.draft_count}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button asChild variant="link">
                        <Link to={`/tools/${tool.id}`}>Versions</Link>
                      </Button>
                      {canManage && !isSystemTool && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Actions for ${tool.name}`}
                            >
                              <MoreHorizontal />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuGroup>
                              <DropdownMenuItem
                                variant="destructive"
                                onSelect={() => void openDeleteModal(tool)}
                              >
                                <Trash2 />
                                Delete tool
                              </DropdownMenuItem>
                            </DropdownMenuGroup>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </LoadState>

      {/* Delete Tool Modal */}
      <Dialog
        open={Boolean(toolToDelete)}
        onOpenChange={(isOpen) => {
          if (!isOpen && !deleting) setToolToDelete(null);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="size-5" />
              Delete Tool
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to permanently delete{" "}
              <strong>{toolToDelete?.name}</strong>?
            </DialogDescription>
          </DialogHeader>

          {loadingImpact ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              Checking tool dependencies across agents…
            </div>
          ) : impact ? (
            <div className="flex flex-col gap-3 rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-xs">
              <div>
                Versions to delete:{" "}
                <span className="font-bold text-foreground">
                  {impact.versions_count}
                </span>
              </div>

              {(impact.bound_agents ?? []).length > 0 ? (
                <div className="space-y-1.5 pt-1 text-destructive">
                  <div className="font-semibold uppercase tracking-wider">
                    Bound Agents Affected:
                  </div>
                  <ul className="list-inside list-disc space-y-1">
                    {(impact.bound_agents ?? []).map((ag, idx) => (
                      <li key={idx}>
                        <strong>{ag.agent_name}</strong> (v{ag.version} -{" "}
                        {ag.status})
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-muted-foreground">
                    Deleting removes its bindings, flow actions, and explicit
                    prompt references from every affected draft and published
                    agent version. Published versions are updated in this dev
                    workspace; historical call evidence is retained.
                  </p>
                </div>
              ) : (
                <div className="text-muted-foreground">
                  <p>No saved agent versions currently reference this tool.</p>
                  <p className="mt-2">
                    Deletion still checks and removes stale prompt/config
                    references; historical call evidence is retained.
                  </p>
                </div>
              )}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              variant="outline"
              disabled={deleting}
              onClick={() => setToolToDelete(null)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting || loadingImpact}
              onClick={confirmDelete}
            >
              {deleting ? "Deleting…" : "Delete tool"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
}
