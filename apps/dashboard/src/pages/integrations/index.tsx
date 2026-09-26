import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Pencil, Trash2 } from "lucide-react";
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

type CalendarIntegration = { id: string; display_name: string; provider: "google_calendar"; calendar_id: string; timezone: string; status: string; connected_at?: string | null; last_error?: string | null };

export type Connection = {
  id: string;
  label: string;
  provider: "whatsapp";
  enabled: boolean;
  config: { phone_number_id: string; waba_id: string; api_version: string };
  secret_names: string[];
  updated_at?: string;
  created_at?: string;
  webhook_url?: string | null;
};

export function IntegrationsPage() {
  const api = useApi();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource<{
    connections: Connection[];
  }>("/integrations");
  const calendars = useResource<{ integrations: CalendarIntegration[] }>("/calendar-integrations");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [phoneId, setPhoneId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [calendarLabel, setCalendarLabel] = useState("My Google Calendar");
  async function connectCalendar() {
    try {
      const result = await api<{ authorization_url: string }>("/calendar-integrations/google/connect", { method: "POST", body: JSON.stringify({ display_name: calendarLabel.trim() || "My Google Calendar", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" }) });
      window.location.assign(result.authorization_url);
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not connect calendar"); }
  }
  async function renameCalendar(calendar: CalendarIntegration) {
    const displayName = window.prompt("Calendar name", calendar.display_name)?.trim();
    if (!displayName || displayName === calendar.display_name) return;
    try {
      await api(`/calendar-integrations/${calendar.id}`, { method: "PATCH", body: JSON.stringify({ display_name: displayName }) });
      toast.success("Calendar name updated");
      await calendars.reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not rename calendar integration");
    }
  }  async function discardCalendar(id: string) {
    if (!window.confirm("Discard this Google Calendar integration?")) return;
    try {
      await api(`/calendar-integrations/${id}`, { method: "DELETE" });
      toast.success("Calendar integration discarded");
      await calendars.reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not discard calendar integration");
    }
  }
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api<Connection>("/integrations", {
        method: "POST",
        body: JSON.stringify({
          label: label.trim(),
          provider: "whatsapp",
          enabled: false,
          config: {
            phone_number_id: phoneId.trim(),
            waba_id: wabaId.trim(),
            api_version: apiVersion.trim(),
          },
        }),
      });
      toast.success("Connection created, disabled until credentials are added");
      setOpen(false);
      await reload();
      navigate(`/integrations/${result.id}`);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not create connection",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title="Integrations"
        description="Action-provider accounts. Model-provider keys stay in server environment."
        action={
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button>New WhatsApp connection</Button>
            </SheetTrigger>
            <SheetContent>
              <form onSubmit={create} className="flex h-full flex-col gap-6">
                <SheetHeader>
                  <SheetTitle>WhatsApp connection</SheetTitle>
                  <SheetDescription>
                    Enter Meta account identifiers. Connection starts disabled.
                  </SheetDescription>
                </SheetHeader>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="wa-label">Label</FieldLabel>
                    <Input
                      id="wa-label"
                      value={label}
                      onChange={(event) => setLabel(event.target.value)}
                      required
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="wa-phone-id">
                      Phone number ID
                    </FieldLabel>
                    <Input
                      id="wa-phone-id"
                      inputMode="numeric"
                      pattern="[0-9]+"
                      value={phoneId}
                      onChange={(event) => setPhoneId(event.target.value)}
                      required
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="wa-waba-id">WABA ID</FieldLabel>
                    <Input
                      id="wa-waba-id"
                      inputMode="numeric"
                      pattern="[0-9]+"
                      value={wabaId}
                      onChange={(event) => setWabaId(event.target.value)}
                      required
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="wa-api-version">
                      Meta API version
                    </FieldLabel>
                    <Input
                      id="wa-api-version"
                      pattern="v[0-9]+\.0"
                      placeholder="vXX.0"
                      value={apiVersion}
                      onChange={(event) => setApiVersion(event.target.value)}
                      required
                    />
                    <FieldDescription>
                      Use the version enabled for your Meta app. No UI default
                      is assumed.
                    </FieldDescription>
                  </Field>
                </FieldGroup>
                <SheetFooter className="mt-auto">
                  <Button type="submit" disabled={busy}>
                    {busy ? "Creating…" : "Create connection"}
                  </Button>
                </SheetFooter>
              </form>
            </SheetContent>
          </Sheet>
        }
      />
      <section className="mb-8 rounded-lg border p-5">
        <div className="flex items-end justify-between gap-4">
          <div><h2 className="font-semibold">Calendar integrations</h2><p className="text-sm text-muted-foreground">Connect employee Google Calendars for human callback scheduling. OAuth tokens stay on the server.</p></div>
          <div className="flex items-center gap-2"><Input aria-label="New calendar name" value={calendarLabel} onChange={(event) => setCalendarLabel(event.target.value)} placeholder="e.g. Omkar work calendar" /><Button onClick={() => void connectCalendar()}>Connect Google Calendar</Button></div>
        </div>
        <div className="mt-4 grid gap-2">
          {calendars.data?.integrations.map((calendar) => <div key={calendar.id} className="flex items-center justify-between rounded-md bg-muted/40 px-3 py-2 text-sm"><div className="flex items-center gap-3"><span>{calendar.display_name} · {calendar.calendar_id}</span><StatusBadge value={calendar.status} /></div><div className="flex items-center gap-1"><Button variant="ghost" size="icon" aria-label={`Rename ${calendar.display_name}`} onClick={() => void renameCalendar(calendar)}><Pencil className="size-4" /></Button><Button variant="ghost" size="icon" aria-label={`Discard ${calendar.display_name}`} onClick={() => void discardCalendar(calendar.id)}><Trash2 className="size-4" /></Button></div></div>)}
          {calendars.data?.integrations.length === 0 && <p className="text-sm text-muted-foreground">No Google Calendars connected.</p>}
        </div>
      </section>
      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.connections.length === 0
            ? "No action integrations configured."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Connection</TableHead>
              <TableHead>State</TableHead>
              <TableHead>Credentials</TableHead>
              <TableHead className="text-right">Open</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.connections.map((connection) => (
              <TableRow key={connection.id}>
                <TableCell className="font-medium">
                  {connection.label}
                </TableCell>
                <TableCell>
                  <StatusBadge
                    value={connection.enabled ? "enabled" : "disabled"}
                  />
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {connection.secret_names.join(", ") || "None"}
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild variant="link">
                    <Link to={`/integrations/${connection.id}`}>Manage</Link>
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
