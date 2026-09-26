import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResource } from "@/lib/resources";

import { AlertTriangle, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Version = {
  id: string;
  version: number;
  revision: number;
  status: string;
  note: string | null;
};
type Agent = { id: string; name: string; active_version_id: string | null };

type AgentImpact = {
  agent_id: string;
  name: string;
  versions_count: number;
  runs_count: number;
  can_delete: boolean;
  warnings: string[];
};

export function AgentDetailPage() {
  const { agentId = "" } = useParams();
  const api = useApi();
  const navigate = useNavigate();
  const agents = useResource<{ agents: Agent[] }>("/agents");
  const versions = useResource<{ versions: Version[] }>(
    `/agents/${agentId}/versions`,
  );
  const [busy, setBusy] = useState<string | null>(null);
  const agent = agents.data?.agents.find((item) => item.id === agentId);

  // Deletion modal state
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [impact, setImpact] = useState<AgentImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function openDeleteModal() {
    setDeleteOpen(true);
    setLoadingImpact(true);
    setImpact(null);
    try {
      const data = await api<AgentImpact>(`/agents/${agentId}/impact`);
      setImpact(data);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not inspect agent impact",
      );
    } finally {
      setLoadingImpact(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    try {
      await api(`/agents/${agentId}?force=true`, {
        method: "DELETE",
      });
      toast.success(`Agent "${agent?.name ?? ""}" deleted`);
      setDeleteOpen(false);
      navigate("/agents");
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not delete agent",
      );
    } finally {
      setDeleting(false);
    }
  }

  async function action(
    version: Version,
    kind: "clone" | "publish" | "activate",
  ) {
    setBusy(version.id);
    try {
      if (kind === "activate") {
        await api(`/agents/${agentId}/activate`, {
          method: "POST",
          body: JSON.stringify({ version_id: version.id }),
        });
        await agents.reload();
      } else {
        const path = `/agent-versions/${version.id}/${kind}`;
        const result = await api<{ id: string }>(path, {
          method: "POST",
          body: JSON.stringify({ revision: version.revision }),
        });
        if (kind === "clone")
          navigate(`/agents/${agentId}/versions/${result.id}`);
        await versions.reload();
      }
      toast.success(
        kind === "clone"
          ? "Draft cloned"
          : kind === "publish"
            ? "Version published"
            : "Version activated",
      );
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title={agent?.name ?? "Agent"}
        description="Version history. Published configurations are immutable."
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:bg-destructive/10 hover:text-destructive gap-1.5"
              onClick={openDeleteModal}
            >
              <Trash2 className="size-4" />
              Delete agent
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/agents">All agents</Link>
            </Button>
          </div>
        }
      />
      <LoadState
        loading={agents.loading || versions.loading}
        error={agents.error || versions.error}
        empty={
          versions.data?.versions.length === 0
            ? "No versions found."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Version</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Note</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {versions.data?.versions.map((version) => (
              <TableRow key={version.id}>
                <TableCell>
                  <Link
                    className="font-medium text-primary hover:underline"
                    to={`/agents/${agentId}/versions/${version.id}`}
                  >
                    v{version.version}
                  </Link>
                  {agent?.active_version_id === version.id && (
                    <span className="ml-2 text-xs text-muted-foreground">
                      Active
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  <StatusBadge value={version.status} />
                </TableCell>
                <TableCell className="max-w-64 truncate text-muted-foreground">
                  {version.note || "No note"}
                </TableCell>
                <TableCell className="flex justify-end gap-1">
                  <Button size="sm" variant="ghost" asChild>
                    <Link to={`/agents/${agentId}/versions/${version.id}`}>
                      {version.status === "draft" ? "Edit" : "View"}
                    </Link>
                  </Button>
                  {version.status === "draft" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === version.id}
                      onClick={() => void action(version, "publish")}
                    >
                      Publish
                    </Button>
                  )}
                  {version.status === "published" && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy === version.id}
                      onClick={() => void action(version, "clone")}
                    >
                      Clone draft
                    </Button>
                  )}
                  {version.status === "published" &&
                    agent?.active_version_id !== version.id && (
                      <Button
                        size="sm"
                        disabled={busy === version.id}
                        onClick={() => void action(version, "activate")}
                      >
                        Activate
                      </Button>
                    )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>

      {/* Delete Agent Modal */}
      <Dialog
        open={deleteOpen}
        onOpenChange={(isOpen) => {
          if (!isOpen && !deleting) setDeleteOpen(false);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="size-5" />
              Delete Agent
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to permanently delete{" "}
              <strong>{agent?.name}</strong>?
            </DialogDescription>
          </DialogHeader>

          {loadingImpact ? (
            <div className="py-6 text-center text-sm text-muted-foreground">
              Checking agent dependencies and call history…
            </div>
          ) : impact ? (
            <div className="flex flex-col gap-3 rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-xs">
              <div className="grid grid-cols-2 gap-2 font-medium">
                <div>
                  Versions to delete:{" "}
                  <span className="font-bold text-foreground">
                    {impact.versions_count}
                  </span>
                </div>
                <div>
                  Historical runs:{" "}
                  <span className="font-bold text-foreground">
                    {impact.runs_count}
                  </span>
                </div>
              </div>

              {impact.warnings.length > 0 && (
                <div className="space-y-1.5 pt-1 text-destructive">
                  <div className="font-semibold uppercase tracking-wider">
                    Side Effects:
                  </div>
                  <ul className="list-inside list-disc space-y-1">
                    {impact.warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              variant="outline"
              disabled={deleting}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleting || loadingImpact}
              onClick={confirmDelete}
            >
              {deleting ? "Deleting…" : "Delete permanently"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
}

