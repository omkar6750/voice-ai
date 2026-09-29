import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, PhoneCall, Play } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { AdminOnly, useOrganizationAccess } from "@/app/access";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
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

type CallbackRecord = {
  id: string;
  contact_id: string;
  contact_name: string | null;
  contact_phone: string | null;
  agent_version_id: string;
  agent_version_number: number | null;
  due_at: string | null;
  timezone: string;
  original_phrase: string;
  status: string;
  automatic_attempts: number;
  call_id: string | null;
  run_id: string | null;
  last_error: string | null;
  claimed_at: string | null;
  completed_at: string | null;
  created_at: string | null;
};

type CallbacksResponse = {
  callbacks: CallbackRecord[];
  total: number;
  automatic_callbacks_enabled: boolean;
  callback_due_window_minutes: number;
};

type DialOptions = {
  endpoints: Array<{
    id: string;
    name: string;
    active_run_id?: string | null;
  }>;
};

export function CallbacksPage() {
  const api = useApi();
  const { canManage } = useOrganizationAccess();
  const [filter, setFilter] = useState<string>("all");
  const url = filter === "all" ? "/callbacks" : `/callbacks?status=${filter}`;
  const { data, loading, error, reload } = useResource<CallbacksResponse>(url);
  const dialOptions = useResource<DialOptions>("/dial-options", canManage);

  const [selectedCallback, setSelectedCallback] =
    useState<CallbackRecord | null>(null);
  const [selectedEndpoint, setSelectedEndpoint] = useState<string>("");
  const [launchBusy, setLaunchBusy] = useState(false);

  const availableEndpoints =
    dialOptions.data?.endpoints.filter((ep) => !ep.active_run_id) ?? [];

  async function launchCallback() {
    if (!selectedCallback || !selectedEndpoint) return;
    setLaunchBusy(true);
    try {
      const res = await api<{ run_id: string; call_id: string }>(
        `/callbacks/${selectedCallback.id}/launch`,
        {
          method: "POST",
          body: JSON.stringify({
            endpoint_id: selectedEndpoint,
            mode: "manual",
          }),
        },
      );
      toast.success("Callback launched");
      setSelectedCallback(null);
      setSelectedEndpoint("");
      await reload();
      if (res.run_id) {
        window.location.href = `/runs/${res.run_id}`;
      }
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Failed to launch callback",
      );
    } finally {
      setLaunchBusy(false);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title="Callbacks"
        description="Scheduled return calls requested by callers. Pinned to explicit contact, agent version, and due time."
      />

      {data && (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border bg-card p-4 text-card-foreground">
          <div className="flex items-center gap-3">
            <CalendarClock className="size-5 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium">Automatic Dispatch Engine</p>
              <p className="text-xs text-muted-foreground">
                {data.automatic_callbacks_enabled
                  ? `Active · Automatic due window: ±${data.callback_due_window_minutes} min`
                  : "Disabled in Workspace Settings · Manual launch only"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={
                data.automatic_callbacks_enabled ? "default" : "secondary"
              }
            >
              {data.automatic_callbacks_enabled ? "Automation On" : "Manual Only"}
            </Badge>
            <span className="text-xs text-muted-foreground">
              Total: {data.total}
            </span>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-b pb-2">
        {["all", "scheduled", "queued", "completed", "uncertain"].map(
          (status) => (
            <Button
              key={status}
              type="button"
              size="sm"
              variant={filter === status ? "secondary" : "ghost"}
              onClick={() => setFilter(status)}
              className="capitalize"
            >
              {status}
            </Button>
          ),
        )}
      </div>

      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.callbacks.length === 0
            ? "No callbacks found matching filter."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Contact</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Due at</TableHead>
              <TableHead>Original Phrase</TableHead>
              <TableHead>Version</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.callbacks.map((cb) => (
              <TableRow key={cb.id}>
                <TableCell className="font-medium">
                  {cb.contact_name ? (
                    <Link
                      to={`/contacts/${cb.contact_id}`}
                      className="hover:underline"
                    >
                      {cb.contact_name}
                    </Link>
                  ) : (
                    cb.contact_id.slice(0, 8)
                  )}
                </TableCell>
                <TableCell>{cb.contact_phone || "—"}</TableCell>
                <TableCell>
                  <div className="text-sm">
                    {cb.due_at
                      ? new Date(cb.due_at).toLocaleString(undefined, {
                          timeZone: cb.timezone || undefined,
                          dateStyle: "short",
                          timeStyle: "short",
                        })
                      : "Unset"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {cb.timezone}
                  </div>
                </TableCell>
                <TableCell className="max-w-xs truncate text-xs text-muted-foreground" title={cb.original_phrase}>
                  “{cb.original_phrase}”
                </TableCell>
                <TableCell>
                  {cb.agent_version_number ? `v${cb.agent_version_number}` : "—"}
                </TableCell>
                <TableCell>
                  <StatusBadge value={cb.status} />
                </TableCell>
                <TableCell className="text-right">
                  {cb.status === "scheduled" && canManage ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setSelectedCallback(cb);
                        setSelectedEndpoint(
                          availableEndpoints[0]?.id || "",
                        );
                      }}
                    >
                      <Play className="mr-1 size-3.5" />
                      Launch
                    </Button>
                  ) : cb.run_id ? (
                    <Button asChild size="sm" variant="ghost">
                      <Link to={`/runs/${cb.run_id}`}>View Run</Link>
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>

      {/* Manual Launch Sheet */}
      <AdminOnly><Sheet
        open={Boolean(selectedCallback)}
        onOpenChange={(open) => !open && setSelectedCallback(null)}
      >
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Launch Callback</SheetTitle>
            <SheetDescription>
              Select an available modem runtime endpoint to place this return call now.
            </SheetDescription>
          </SheetHeader>

          {selectedCallback && (
            <div className="mt-6 flex flex-col gap-5">
              <div className="rounded-md border p-3 text-sm">
                <p className="font-semibold text-foreground">
                  {selectedCallback.contact_name || "Contact"}
                </p>
                <p className="text-muted-foreground">{selectedCallback.contact_phone}</p>
                <p className="mt-2 text-xs italic text-muted-foreground">
                  “{selectedCallback.original_phrase}”
                </p>
              </div>

              <Field>
                <FieldLabel htmlFor="callback-endpoint">
                  Runtime Endpoint
                </FieldLabel>
                <NativeSelect
                  id="callback-endpoint"
                  value={selectedEndpoint}
                  onChange={(e) => setSelectedEndpoint(e.target.value)}
                >
                  <option value="">Select an endpoint...</option>
                  {dialOptions.data?.endpoints.map((ep) => (
                    <option
                      key={ep.id}
                      value={ep.id}
                      disabled={Boolean(ep.active_run_id)}
                    >
                      {ep.name} {ep.active_run_id ? "(Occupied)" : "(Available)"}
                    </option>
                  ))}
                </NativeSelect>
                <FieldDescription>
                  Uncertain attempts are never redialed automatically.
                </FieldDescription>
              </Field>

              <SheetFooter className="mt-auto">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setSelectedCallback(null)}
                >
                  Cancel
                </Button>
                <Button
                  type="button"
                  disabled={!selectedEndpoint || launchBusy}
                  onClick={() => void launchCallback()}
                >
                  <PhoneCall className="mr-1.5 size-4" />
                  {launchBusy ? "Launching…" : "Dial Now"}
                </Button>
              </SheetFooter>
            </div>
          )}
        </SheetContent>
      </Sheet></AdminOnly>
    </PageBody>
  );
}
