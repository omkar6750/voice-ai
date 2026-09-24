import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AudioLines, ChevronRight, Plus, RefreshCw, Sparkles } from "lucide-react";
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

interface AgentItem {
  id: string;
  name: string;
  active_version_id: string | null;
}

export function AgentsPage() {
  const api = useApi();
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await api<{ agents: AgentItem[] }>("/agents");
      setAgents(data.agents);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load agents";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Agents</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Autonomous conversational voice agents, prompt flows, and versioned pipelines.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <Card key={n} className="p-4">
              <Skeleton className="h-5 w-32 mb-2" />
              <Skeleton className="h-4 w-48 mb-4" />
              <Skeleton className="h-8 w-20" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Could not load agents</EmptyTitle>
            <EmptyDescription>{error}</EmptyDescription>
          </EmptyHeader>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </Empty>
      ) : agents.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No agents configured</EmptyTitle>
            <EmptyDescription>
              Create or seed an agent to start placing and handling autonomous voice calls.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <Card
              key={agent.id}
              className="group flex flex-col justify-between hover:border-border transition-colors shadow-none"
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex size-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <AudioLines className="size-4" />
                  </div>
                  {agent.active_version_id ? (
                    <Badge variant="outline" className="bg-emerald-50 text-emerald-700 text-[11px] font-normal border-emerald-200">
                      Active Version
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground text-[11px] font-normal">
                      Draft Only
                    </Badge>
                  )}
                </div>
                <CardTitle className="text-sm font-semibold mt-3 group-hover:text-primary transition-colors">
                  {agent.name}
                </CardTitle>
                <CardDescription className="text-xs line-clamp-1 font-mono">
                  ID: {agent.id.slice(0, 12)}…
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Button asChild variant="outline" size="sm" className="w-full justify-between text-xs">
                  <Link to={`/agents/${agent.id}`}>
                    Manage versions
                    <ChevronRight className="size-3.5 text-muted-foreground" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
