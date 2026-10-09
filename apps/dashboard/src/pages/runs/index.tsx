import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@clerk/react";
import { Link } from "react-router-dom";
import { Search, RefreshCw, Activity } from "lucide-react";
import { toast } from "sonner";
import { useApi, useSupportSession } from "@/app/api";
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
import type { components } from "@/generated/api";

function formatProvider(provider?: string) {
  if (!provider) return "SIM7600";
  const lower = provider.toLowerCase();
  if (lower === "dashboard" || lower === "browser") return "Dashboard";
  if (lower === "twilio" || lower === "twilio_voice") return "Twilio";
  if (lower === "sim7600") return "SIM7600";
  return provider;
}

export function RunsPage() {
  const api = useApi();
  const { orgId, userId } = useAuth();
  const support = useSupportSession();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [storedCursors, setCursors] = useState<string[]>([]);
  const scope = JSON.stringify([userId, orgId, support]);
  const cursorScope = useRef(scope);
  const cursors = cursorScope.current === scope ? storedCursors : [];
  useEffect(() => { cursorScope.current = scope; setCursors([]); }, [scope]);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (search.trim() !== debouncedSearch) {
        setDebouncedSearch(search.trim());
        setCursors([]);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [search, debouncedSearch]);
  const parameters = new URLSearchParams({ limit: "25" });
  if (status !== "all") parameters.set("status", status);
  if (debouncedSearch) parameters.set("search", debouncedSearch);
  if (cursors.length) parameters.set("cursor", cursors[cursors.length - 1]);
  const queryKey = ["runs", userId, orgId, support, parameters.toString()];
  const runsQuery = useQuery({
    queryKey,
    enabled: Boolean(userId && orgId),
    queryFn: ({ signal }) =>
      api<components["schemas"]["RunPageResponse"]>(`/runs?${parameters}`, {
        signal,
      }),
    staleTime: 5_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.runs.some((run) => isActive(run.status)) ? 10_000 : false;
    },
  });
  const runs = runsQuery.data?.runs ?? [];
  const loading = runsQuery.isPending;
  const error = runsQuery.error?.message ?? "";
  const lastNotifiedError = useRef("");
  useEffect(() => {
    if (!error) {
      lastNotifiedError.current = "";
      return;
    }
    if (error !== lastNotifiedError.current) {
      toast.error(error);
      lastNotifiedError.current = error;
    }
  }, [error]);
  const visible = runs;
  const statuses = [
    "queued",
    "claimed",
    "running",
    "uncertain",
    "completed",
    "failed",
    "cancelled",
  ];
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 p-4 lg:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Execution
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
          <p className="text-sm text-muted-foreground">
            Page {cursors.length + 1}, {runs.length} executions
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => { setCursors([]); void queryClient.invalidateQueries({ queryKey: ["runs", userId, orgId, support] }); }}
          disabled={runsQuery.isFetching}
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
          onChange={(event) => {
            setStatus(event.target.value);
            setCursors([]);
          }}
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
                <TableHead>Provider</TableHead>
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
                    </div>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium">
                      {formatProvider(run.transport_provider ?? run.channel)}
                    </span>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-muted-foreground">
                    {stamp(run.started_at ?? run.created_at)}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={run.status} outcome={run.call_outcome} />
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
          Showing {visible.length} runs on this page. Active states refresh
          every 10 seconds.
        </p>
      )}
      <nav aria-label="Run pages" className="flex items-center justify-between">
        <Button
          variant="outline"
          disabled={!cursors.length || runsQuery.isFetching}
          onClick={() => setCursors((old) => old.slice(0, -1))}
        >
          Previous
        </Button>
        <Button
          variant="outline"
          disabled={!runsQuery.data?.has_more || runsQuery.isFetching}
          onClick={() => {
            const next = runsQuery.data?.next_cursor;
            if (next) setCursors((old) => [...old, next]);
          }}
        >
          Next
        </Button>
      </nav>
    </div>
  );
}
