import { ArrowRight, AudioLines, Radio, UsersRound } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useApi } from "../app/api";
import { Island, Notice, Status } from "../components/ui";

type Agent = { id: string; name: string; active_version_id: string | null };
type Run = { id: string; status: string; channel: string; created_at: string };

export function OverviewPage() {
  const api = useApi();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api<{ agents: Agent[] }>("/agents"),
      api<{ runs: Run[] }>("/runs"),
    ])
      .then(([a, r]) => {
        setAgents(a.agents);
        setRuns(r.runs);
      })
      .catch((cause) =>
        setError(
          cause instanceof Error ? cause.message : "Could not load overview",
        ),
      );
  }, [api]);
  const recent = runs.slice(0, 5);
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-medium text-primary">Workspace</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Agents and recent execution. Counts reflect records currently returned
          by the API.
        </p>
      </div>
      {error && <Notice text={error} error />}
      <div className="grid gap-4 sm:grid-cols-3">
        {[
          {
            label: "Agents",
            value: agents.length,
            icon: AudioLines,
            path: "/agents",
          },
          {
            label: "Active versions",
            value: agents.filter((a) => a.active_version_id).length,
            icon: Radio,
            path: "/agents",
          },
          {
            label: "Runs",
            value: runs.length,
            icon: UsersRound,
            path: "/runs",
          },
        ].map(({ label, value, icon: Icon, path }) => (
          <Link
            to={path}
            key={label}
            className="rounded-lg border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary/40"
          >
            <div className="flex items-start justify-between">
              <p className="text-sm text-muted-foreground">{label}</p>
              <Icon size={18} className="text-muted-foreground" />
            </div>
            <p className="mt-4 text-3xl font-semibold tabular-nums">{value}</p>
          </Link>
        ))}
      </div>
      <Island
        title="Recent runs"
        description="Latest execution records."
        action={
          <Link
            to="/runs"
            className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            View all <ArrowRight size={15} />
          </Link>
        }
      >
        {recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">No runs yet.</p>
        ) : (
          <div className="divide-y divide-border">
            {recent.map((run) => (
              <Link
                key={run.id}
                to={`/runs/${run.id}`}
                className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0 hover:text-primary"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{run.id}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {run.channel} · {new Date(run.created_at).toLocaleString()}
                  </p>
                </div>
                <Status value={run.status} />
              </Link>
            ))}
          </div>
        )}
      </Island>
    </div>
  );
}
