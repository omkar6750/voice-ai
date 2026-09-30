import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@clerk/react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Pencil, Trash2 } from "lucide-react";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
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
  provider: "whatsapp" | "twilio_voice";
  enabled: boolean;
  config: Record<string, any>;
  secret_names: string[];
  updated_at?: string;
  created_at?: string;
  webhook_url?: string | null;
  deleted_at?: string | null;
  credential_id?: string | null;
};

export function IntegrationsPage() {
  const api = useApi();
  const { orgId } = useAuth();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource<{
    connections: Connection[];
  }>("/integrations");
  const calendars = useResource<{ integrations: CalendarIntegration[] }>("/calendar-integrations");
  const [open, setOpen] = useState(false);
  const [newType, setNewType] = useState<"whatsapp" | "twilio_voice">("twilio_voice");
  const hasActiveWhatsapp = Boolean(
    data?.connections.some((c) => c.provider === "whatsapp" && !c.deleted_at),
  );
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [phoneId, setPhoneId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [accountSid, setAccountSid] = useState("");
  const [twilioCredentials, setTwilioCredentials] = useState<components["schemas"]["CredentialStatus"][]>([]);
  const [twilioCredentialId, setTwilioCredentialId] = useState("");
  const [whatsappCredentialId, setWhatsappCredentialId] = useState("");
  const [whatsappCredentials, setWhatsappCredentials] = useState<components["schemas"]["CredentialStatus"][]>([]);
  const [calendarLabel, setCalendarLabel] = useState("My Google Calendar");
  useEffect(() => {
    let active = true;
    if (!orgId) { setTwilioCredentials([]); setWhatsappCredentials([]); return () => { active = false; }; }
    void api<components["schemas"]["CredentialStatus"][]>(`/orgs/${orgId}/credentials`)
      .then((rows) => { if (active) {
        setTwilioCredentials(rows.filter((row) => row.provider === "twilio" && row.status === "stored"));
        setWhatsappCredentials(rows.filter((row) => row.provider === "whatsapp" && row.status === "stored"));
      } })
      .catch(() => { if (active) { setTwilioCredentials([]); setWhatsappCredentials([]); } });
    return () => { active = false; };
  }, [api, orgId]);
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
      const payload =
        newType === "twilio_voice"
          ? {
              label: label.trim(),
              provider: "twilio_voice",
              enabled: false,
              credential_id: twilioCredentialId,
              config: {
                account_sid: accountSid.trim(),
                phone_numbers: [],
              },
            }
          : {
              label: label.trim(),
              provider: "whatsapp",
              enabled: false,
              credential_id: whatsappCredentialId,
              config: {
                phone_number_id: phoneId.trim(),
                waba_id: wabaId.trim(),
                api_version: apiVersion.trim(),
              },
            };

      const result = await api<Connection>("/integrations", {
        method: "POST",
        body: JSON.stringify(payload),
      });

      if (newType === "twilio_voice" && twilioCredentialId) {
        try {
          const testRes = await api<{
            status: "ok" | "warning";
            account_type?: string;
            phone_numbers?: Array<{ phone_number: string; friendly_name: string; voice: boolean; sid: string }>;
            message?: string;
          }>(`/integrations/${result.id}/test`, { method: "POST" });

          if (testRes.status === "ok") {
            const synced = await api<{
              phone_numbers: Array<{ phone_number: string; friendly_name: string; voice: boolean; sid: string }>;
            }>(`/integrations/${result.id}/refresh-numbers`, { method: "POST" });
            await api<Connection>(`/integrations/${result.id}`, {
              method: "PATCH",
              body: JSON.stringify({ enabled: true }),
            });
            toast.success(
              `Twilio Voice connected! (${synced.phone_numbers.length} voice numbers found)`,
            );
          } else {
            toast.warning(
              `Twilio connection was created but remains disabled. ${testRes.message || "This account is not ready for voice calls."}`,
              { duration: 8000 },
            );
          }
        } catch (cause) {
          toast.error(
            `Twilio connection was created but remains disabled: ${cause instanceof Error ? cause.message : "verification failed"}`,
            { duration: 8000 },
          );
        }
      } else {
        toast.success("Connection created, disabled until credentials are added");
      }

      setOpen(false);
      setLabel("");
      setAccountSid("");
      setTwilioCredentialId("");
      setWhatsappCredentialId("");
      setPhoneId("");
      setWabaId("");
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
        description="Connect organization-owned provider credentials to the integrations that use them."
        action={
          <div className="flex items-center gap-2">
            <Sheet open={open} onOpenChange={setOpen}>
              <SheetTrigger asChild>
                <Button>New connection</Button>
              </SheetTrigger>
              <SheetContent>
                <form onSubmit={create} className="flex h-full flex-col gap-6">
                  <SheetHeader>
                    <SheetTitle>New integration</SheetTitle>
                    <SheetDescription>
                      Connect Twilio Voice for calling or Meta for WhatsApp messaging.
                    </SheetDescription>
                  </SheetHeader>
                  <FieldGroup>
                    <Field>
                      <FieldLabel>Integration provider</FieldLabel>
                      <div className="flex items-center gap-4 py-1">
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                          <input
                            type="radio"
                            name="newType"
                            value="twilio_voice"
                            checked={newType === "twilio_voice"}
                            onChange={() => setNewType("twilio_voice")}
                          />
                          <span>Twilio Voice</span>
                        </label>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                          <input
                            type="radio"
                            name="newType"
                            value="whatsapp"
                            checked={newType === "whatsapp"}
                            disabled={hasActiveWhatsapp}
                            onChange={() => setNewType("whatsapp")}
                          />
                          <span>WhatsApp {hasActiveWhatsapp ? "(Max 1)" : ""}</span>
                        </label>
                      </div>
                    </Field>

                    <Field>
                      <FieldLabel htmlFor="conn-label">Label</FieldLabel>
                      <Input
                        id="conn-label"
                        placeholder={newType === "twilio_voice" ? "Primary Twilio" : "Support WhatsApp"}
                        value={label}
                        onChange={(event) => setLabel(event.target.value)}
                        required
                      />
                    </Field>

                    {newType === "twilio_voice" ? (
                      <>
                        <Field>
                          <FieldLabel htmlFor="twilio-sid">Account SID</FieldLabel>
                          <Input
                            id="twilio-sid"
                            placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                            pattern="^AC[a-zA-Z0-9]{32}$"
                            value={accountSid}
                            onChange={(event) => setAccountSid(event.target.value)}
                            required
                          />
                          <FieldDescription>
                            Starts with AC followed by 32 alphanumeric characters and must match the selected Twilio credential.
                          </FieldDescription>
                        </Field>

                        <Field>
                          <FieldLabel htmlFor="twilio-credential">Named Twilio credential</FieldLabel>
                          <NativeSelect id="twilio-credential" value={twilioCredentialId} required onChange={(event) => setTwilioCredentialId(event.target.value)}>
                            <option value="">Select an organization credential</option>
                            {twilioCredentials.filter((item) => item.status === "stored").map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}
                          </NativeSelect>
                          <FieldDescription>
                            Create the Account SID, REST API key and webhook Auth Token bundle in Organization settings first. {twilioCredentials.length === 0 ? "No active Twilio credential is available." : "The selection is stored by its application credential ID."}
                          </FieldDescription>
                        </Field>
                      </>
                    ) : (
                      <>
                        <Field>
                          <FieldLabel htmlFor="whatsapp-credential">Named WhatsApp credential</FieldLabel>
                          <NativeSelect id="whatsapp-credential" value={whatsappCredentialId} required onChange={(event) => setWhatsappCredentialId(event.target.value)}>
                            <option value="">Select an organization credential</option>
                            {whatsappCredentials.filter((item) => item.status === "stored").map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}
                          </NativeSelect>
                          <FieldDescription>
                            Select the Meta access token you added in Organization settings.
                            {whatsappCredentials.every((item) => item.status !== "stored") && " No active WhatsApp credential is available."}
                          </FieldDescription>
                        </Field>
                        <Field>
                          <FieldLabel htmlFor="wa-phone-id">Phone number ID</FieldLabel>
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
                          <FieldLabel htmlFor="wa-api-version">API version</FieldLabel>
                          <Input
                            id="wa-api-version"
                            placeholder="v23.0"
                            pattern="^v[0-9]+\.0$"
                            value={apiVersion}
                            onChange={(event) => setApiVersion(event.target.value)}
                            required
                          />
                        </Field>
                      </>
                    )}
                  </FieldGroup>
                  <SheetFooter>
                    <Button type="submit" disabled={busy}>
                      {busy ? "Creating…" : "Create connection"}
                    </Button>
                  </SheetFooter>
                </form>
              </SheetContent>
            </Sheet>
          </div>
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
              <TableHead>Provider credential</TableHead>
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
                  {connection.deleted_at ? (
                    <Badge variant="secondary" className="text-muted-foreground">
                      Disconnected
                    </Badge>
                  ) : (
                    <StatusBadge
                      value={connection.enabled ? "enabled" : "disabled"}
                    />
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {connection.credential_id
                    ? [...twilioCredentials, ...whatsappCredentials].find((item) => item.id === connection.credential_id)?.name ?? "Named credential linked"
                    : connection.secret_names.join(", ") || "None"}
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
