import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Search, RefreshCw, Activity } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { isActive, stamp } from "./model";
import { StatusBadge } from "./status";
import type { RunSummary } from "./types";

export function RunsPage() {
  const api = useApi();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const lastNotifiedError = useRef("");
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api<{ runs: RunSummary[] }>("/runs")
        .then((data) => {
          if (cancelled) return;
          setRuns(data.runs);
          setError("");
          lastNotifiedError.current = "";
        })
        .catch((cause) => {
          if (cancelled) return;
          const message =
            cause instanceof Error ? cause.message : "Could not load runs";
          setError(message);
          if (message !== lastNotifiedError.current) {
            toast.error(message);
            lastNotifiedError.current = message;
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };
    load();
    const timer = window.setInterval(load, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api, reload]);
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return runs.filter(
      (run) =>
        (status === "all" || run.status === status) &&
        (!needle ||
          [run.id, run.contact_name, run.channel, run.agent_version_id].some(
            (value) => value?.toLowerCase().includes(needle),
          )),
    );
  }, [runs, search, status]);
  const statuses = [...new Set(runs.map((run) => run.status))].sort();
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-4 lg:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Execution
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
          <p className="text-sm text-muted-foreground">
            {runs.length} stored executions across phone and browser.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => setReload((value) => value + 1)}
        >
          <RefreshCw data-icon="inline-start" /> Refresh
        </Button>
      </header>
      <div className="flex flex-wrap gap-2">
        <label className="relative min-w-48 flex-1">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            aria-label="Search runs"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search run, contact, agent version…"
            className="pl-9"
          />
        </label>
        <NativeSelect
          aria-label="Filter by status"
          value={status}
          onChange={(event) => setStatus(event.target.value)}
        >
          <NativeSelectOption value="all">All states</NativeSelectOption>
          {statuses.map((item) => (
            <NativeSelectOption key={item} value={item}>
              {item.replaceAll("_", " ")}
            </NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
      {loading ? (
        <div className="flex flex-col gap-2" aria-label="Loading runs">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : error && !runs.length ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Activity />
            </EmptyMedia>
            <EmptyTitle>Runs unavailable</EmptyTitle>
            <EmptyDescription>{error}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : !visible.length ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Activity />
            </EmptyMedia>
            <EmptyTitle>No matching runs</EmptyTitle>
            <EmptyDescription>
              {runs.length
                ? "Try another status or search."
                : "No run has been recorded yet."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Contact</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Started</TableHead>
                <TableHead>State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>
                    <Link
                      className="font-medium text-primary hover:underline"
                      to={"/runs/" + run.id}
                    >
                      {run.id.slice(0, 12)}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span className="font-medium text-xs">
                        {run.contact_name ?? "No contact snapshot"}
                      </span>
                      {run.contact_phone && (
                        <span className="font-mono text-[11px] text-muted-foreground">
                          {run.contact_phone}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="capitalize">{run.channel}</TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {stamp(run.started_at ?? run.created_at)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} />
                    {isActive(run.status) && (
                      <span className="sr-only">Active</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      {!loading && visible.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Showing {visible.length} of {runs.length} runs. Active states refresh
          every 10 seconds.
        </p>
      )}
    </div>
  );
}
