import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  CalendarClock,
  CheckCircle,
  Clock,
  PhoneCall,
  Play,
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

interface CallbackItem {
  id: string;
  request_key: string;
  contact_id: string;
  agent_version_id: string;
  due_at: string;
  timezone: string;
  original_phrase: string;
  status: "scheduled" | "queued" | "completed" | "cancelled";
  call_id: string | null;
  automatic_attempts: number;
}

interface ContactItem {
  id: string;
  name: string;
  phone_number: string;
}

export function CallbacksPage() {
  const api = useApi();
  const [callbacks, setCallbacks] = useState<CallbackItem[]>([]);
  const [contacts, setContacts] = useState<Record<string, ContactItem>>({});
  const [endpoints, setEndpoints] = useState<Array<{ id: string; name: string }>>([]);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const [cbData, contactsData, epData] = await Promise.all([
        api<{ callbacks: CallbackItem[] }>("/callbacks"),
        api<{ contacts: ContactItem[] }>("/contacts").catch(() => ({ contacts: [] })),
        api<{ endpoints: Array<{ id: string; name: string }> }>("/runtime-endpoints").catch(() => ({
          endpoints: [],
        })),
      ]);
      const map: Record<string, ContactItem> = {};
      for (const c of contactsData.contacts) {
        map[c.id] = c;
      }
      setContacts(map);
      setCallbacks(cbData.callbacks);
      setEndpoints(epData.endpoints);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load callbacks");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function triggerLaunch(callbackId: string) {
    if (!endpoints.length) {
      toast.error("No runtime endpoint available to place callback");
      return;
    }
    const defaultEndpoint = endpoints[0].id;
    setBusyAction(callbackId);
    try {
      await api(`/callbacks/${callbackId}/launch`, {
        method: "POST",
        body: JSON.stringify({
          endpoint_id: defaultEndpoint,
          mode: "manual",
        }),
      });
      toast.success("Callback dispatched to call queue");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not launch callback");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Callback Schedule</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Confirmed caller callback appointments, timezone commitments, and automatic re-engagement.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <Card className="p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-28 w-full" />
        </Card>
      ) : callbacks.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No callbacks scheduled</EmptyTitle>
            <EmptyDescription>
              When callers ask to be reached back at a specific time, callbacks appear here automatically.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Card className="shadow-none">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Scheduled Due Time</TableHead>
                  <TableHead className="text-xs">Contact</TableHead>
                  <TableHead className="text-xs">Requested Phrase / Reason</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {callbacks.map((cb) => {
                  const contact = contacts[cb.contact_id];
                  const due = new Date(cb.due_at).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  });

                  return (
                    <TableRow key={cb.id}>
                      <TableCell className="text-xs font-mono">
                        <div className="flex items-center gap-1.5">
                          <Clock className="size-3.5 text-muted-foreground" />
                          <span className="font-semibold">{due}</span>
                          <span className="text-[11px] text-muted-foreground">({cb.timezone})</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">
                        <div className="flex flex-col">
                          <span className="font-medium">{contact?.name || cb.contact_id.slice(0, 8)}</span>
                          <span className="font-mono text-[11px] text-muted-foreground">
                            {contact?.phone_number || "—"}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-xs truncate">
                        "{cb.original_phrase}"
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            cb.status === "scheduled"
                              ? "bg-amber-50 text-amber-800 border-amber-200 text-[11px]"
                              : cb.status === "queued"
                                ? "bg-blue-50 text-blue-700 border-blue-200 text-[11px]"
                                : "bg-secondary text-muted-foreground text-[11px]"
                          }
                        >
                          {cb.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {cb.status === "scheduled" && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="text-xs h-7 px-2"
                            disabled={busyAction === cb.id}
                            onClick={() => void triggerLaunch(cb.id)}
                          >
                            <PhoneCall className="size-3 mr-1" /> Call Now
                          </Button>
                        )}
                        {cb.call_id && (
                          <Button asChild variant="link" size="sm" className="text-xs h-7 px-1">
                            <Link to={`/runs`}>View Run</Link>
                          </Button>
                        )}
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
