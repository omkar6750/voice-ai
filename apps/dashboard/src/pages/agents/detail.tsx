import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle,
  Copy,
  ExternalLink,
  Layers,
  Play,
  Plus,
  Radio,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface AgentVersionItem {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  config: any;
  note: string | null;
}

export function AgentDetailPage() {
  const { agentId } = useParams();
  const api = useApi();
  const [versions, setVersions] = useState<AgentVersionItem[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [agentName, setAgentName] = useState<string>("Agent");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  async function load() {
    if (!agentId) return;
    setLoading(true);
    try {
      const [agentsData, versionsData] = await Promise.all([
        api<{ agents: Array<{ id: string; name: string; active_version_id: string | null }> }>("/agents"),
        api<{ versions: AgentVersionItem[] }>(`/agents/${agentId}/versions`),
      ]);
      const current = agentsData.agents.find((a) => a.id === agentId);
      if (current) {
        setAgentName(current.name);
        setActiveVersionId(current.active_version_id);
      }
      setVersions(versionsData.versions);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load agent");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [agentId]);

  async function cloneVersion(versionId: string, revision: number) {
    setBusyAction(versionId);
    try {
      await api<{ version_id: string }>(`/agent-versions/${versionId}/clone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revision }),
      });
      toast.success("Created new draft version");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not clone version");
    } finally {
      setBusyAction(null);
    }
  }

  async function activateVersion(versionId: string) {
    if (!agentId) return;
    setBusyAction(versionId);
    try {
      await api(`/agents/${agentId}/activate`, {
        method: "POST",
        body: JSON.stringify({ version_id: versionId }),
      });
      toast.success("Active version updated");
      setActiveVersionId(versionId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not activate version");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div>
        <Link
          to="/agents"
          className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="size-3.5" /> Back to agents
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-1">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{agentName}</h1>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">
              Agent ID: {agentId}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void load()}>
              <RefreshCw className="size-3.5 mr-1.5" /> Refresh
            </Button>
          </div>
        </div>
      </div>

      {loading ? (
        <Card className="p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-24 w-full" />
        </Card>
      ) : versions.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No versions found</EmptyTitle>
            <EmptyDescription>This agent does not have any versions configured.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Card className="shadow-none">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Version History</CardTitle>
            <CardDescription className="text-xs">
              Published versions are immutable snapshots. Drafts can be edited and published.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs w-24">Version</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs">Flow & Models</TableHead>
                  <TableHead className="text-xs">Notes</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {versions.map((ver) => {
                  const isActive = ver.id === activeVersionId;
                  const cfg = ver.config || {};
                  const llm = cfg.llm?.model ?? "Default LLM";
                  const tts = cfg.tts?.voice ?? "Default Voice";
                  const nodesCount = cfg.flow?.nodes?.length ?? 0;

                  return (
                    <TableRow key={ver.id}>
                      <TableCell className="font-mono text-xs font-semibold">
                        v{ver.version} (r{ver.revision})
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <Badge
                            variant="outline"
                            className={
                              ver.status === "published"
                                ? "bg-emerald-50 text-emerald-700 text-[11px] border-emerald-200"
                                : "bg-secondary text-muted-foreground text-[11px]"
                            }
                          >
                            {ver.status}
                          </Badge>
                          {isActive && (
                            <Badge variant="outline" className="bg-blue-50 text-blue-700 text-[11px] border-blue-200">
                              Active
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        <div className="flex flex-col gap-0.5 font-mono text-[11px]">
                          <span>{nodesCount} flow nodes</span>
                          <span className="text-foreground/80">{llm} · {tts}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {ver.note || "No release notes"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {ver.status === "published" && !isActive && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-xs h-7 px-2"
                              disabled={busyAction === ver.id}
                              onClick={() => void activateVersion(ver.id)}
                            >
                              Make Active
                            </Button>
                          )}
                          {ver.status === "published" && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="text-xs h-7 px-2"
                              disabled={busyAction === ver.id}
                              onClick={() => void cloneVersion(ver.id, ver.revision)}
                            >
                              <Copy className="size-3 mr-1" /> Clone Draft
                            </Button>
                          )}
                          <Button asChild variant="outline" size="sm" className="text-xs h-7 px-2">
                            <Link to={`/agents/${agentId}/versions/${ver.id}`}>
                              {ver.status === "draft" ? "Edit Draft" : "View Snapshot"}
                              <ExternalLink className="size-3 ml-1" />
                            </Link>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
