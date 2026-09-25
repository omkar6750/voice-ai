import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { PageBody, PageHeader, LoadState } from "@/components/record-page";
import { Button } from "@/components/ui/button";
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

export function AgentsPage() {
  const api = useApi();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource<{ agents: Agent[] }>(
    "/agents",
  );
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    try {
      // Minimal valid draft. Provider defaults come from the backend contract, not a UI registry.
      const result = await api<{ agent_id: string; version_id: string }>(
        "/agents",
        {
          method: "POST",
          body: JSON.stringify({
            name: trimmed,
            config: {
              name: trimmed,
              flow: {
                initial_node: "greeting",
                nodes: [{ id: "greeting", prompt: "", terminal: true }],
              },
            },
          }),
        },
      );
      toast.success("Draft agent created");
      setOpen(false);
      setName("");
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
                </FieldGroup>
                <SheetFooter className="mt-auto">
                  <Button type="submit" disabled={busy || !name.trim()}>
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
              <TableHead className="text-right">Open</TableHead>
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
                  <Button variant="link" asChild>
                    <Link to={`/agents/${agent.id}`}>Versions</Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
    </PageBody>
  );
}
