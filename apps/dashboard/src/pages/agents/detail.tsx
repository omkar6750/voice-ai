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

type Version = {
  id: string;
  version: number;
  revision: number;
  status: string;
  note: string | null;
};
type Agent = { id: string; name: string; active_version_id: string | null };

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
          <Button asChild variant="outline">
            <Link to="/agents">All agents</Link>
          </Button>
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
    </PageBody>
  );
}
