import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import { PageBody, PageHeader, LoadState } from "@/components/record-page";
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
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResource } from "@/lib/resources";

type Agent = { id: string; name: string; active_version_id: string | null };

type AgentImpact = {
  agent_id: string;
  name: string;
  versions_count: number;
  runs_count: number;
  can_delete: boolean;
  warnings: string[];
};

export function AgentsPage() {
  const api = useApi();
  const { canManage } = useOrganizationAccess();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource<{ agents: Agent[] }>(
    "/agents",
  );
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [initialNode, setInitialNode] = useState("opening");
  const [busy, setBusy] = useState(false);

  // Deletion state
  const [agentToDelete, setAgentToDelete] = useState<Agent | null>(null);
  const [impact, setImpact] = useState<AgentImpact | null>(null);
  const [loadingImpact, setLoadingImpact] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    const nodeId = initialNode.trim();
    if (!trimmed || !/^[a-z][a-z0-9_]*$/.test(nodeId)) return;
    setBusy(true);
    try {
      const result = await api<{ agent_id: string; version_id: string }>(
        "/agents",
        {
          method: "POST",
          body: JSON.stringify({
            name: trimmed,
            config: {
              name: trimmed,
              flow: {
                initial_node: nodeId,
                nodes: [{ id: nodeId, role_message: "", task_messages: [], terminal: true }],
              },
            },
          }),
        },
      );
      toast.success("Draft agent created");
      setOpen(false);
      setName("");
      setInitialNode("opening");
      await reload();
      navigate(`/agents/${result.agent_id}/versions/${result.version_id}`);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not create agent",
      );
    } finally {
      setBusy(false);
    }
  }

  async function openDeleteModal(agent: Agent) {
    setAgentToDelete(agent);
    setLoadingImpact(true);
    setImpact(null);
    try {
      const data = await api<AgentImpact>(`/agents/${agent.id}/impact`);
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
    if (!agentToDelete) return;
    setDeleting(true);
    try {
      await api(`/agents/${agentToDelete.id}?force=true`, {
        method: "DELETE",
      });
      toast.success(`Agent "${agentToDelete.name}" deleted`);
      setAgentToDelete(null);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not delete agent",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title="Agents"
        description="Draft, publish, then activate a version for new calls."
        action={
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button>
                <Plus data-icon="inline-start" /> New agent
              </Button>
            </SheetTrigger>
            <SheetContent>
              <form onSubmit={create} className="flex h-full flex-col gap-6">
                <SheetHeader>
                  <SheetTitle>New agent</SheetTitle>
                  <SheetDescription>
                    Create a minimal draft. Configure prompts and flow before
                    publishing.
                  </SheetDescription>
                </SheetHeader>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="agent-name">Name</FieldLabel>
                    <Input
                      id="agent-name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      maxLength={120}
                      required
                    />
                    <FieldDescription>
                      Visible in agent list and run references.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="initial-node-id">Initial node ID</FieldLabel>
                    <Input
                      id="initial-node-id"
                      value={initialNode}
                      onChange={(event) => setInitialNode(event.target.value)}
                      maxLength={64}
                      pattern="[a-z][a-z0-9_]*"
                      required
                    />
                    <FieldDescription>
                      This node opens the call. Use lowercase letters, numbers, and underscores.
                    </FieldDescription>
                  </Field>
                </FieldGroup>
                <SheetFooter className="mt-auto">
                  <Button
                    type="submit"
                    disabled={busy || !name.trim() || !/^[a-z][a-z0-9_]*$/.test(initialNode.trim())}
                  >
                    {busy ? "Creating…" : "Create draft"}
                  </Button>
                </SheetFooter>
              </form>
            </SheetContent>
          </Sheet>
        }
      />
      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.agents.length === 0 ? "Create first draft agent." : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Agent</TableHead>
              <TableHead>Active version</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.agents.map((agent) => (
              <TableRow key={agent.id}>
                <TableCell className="font-medium">{agent.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {agent.active_version_id
                    ? agent.active_version_id.slice(0, 8)
                    : "No active version"}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    <Button variant="link" asChild>
                      <Link to={`/agents/${agent.id}`}>Versions</Link>
                    </Button>
                    {canManage && <Button
                      variant="ghost"
                      size="icon-sm"
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => openDeleteModal(agent)}
                      title={`Delete ${agent.name}`}
                    >
                      <Trash2 className="size-4" />
                      <span className="sr-only">Delete</span>
                    </Button>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>

      {/* Delete Agent Modal */}
      <Dialog
        open={Boolean(agentToDelete)}
        onOpenChange={(isOpen) => {
          if (!isOpen && !deleting) setAgentToDelete(null);
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
              <strong>{agentToDelete?.name}</strong>?
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
              onClick={() => setAgentToDelete(null)}
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
