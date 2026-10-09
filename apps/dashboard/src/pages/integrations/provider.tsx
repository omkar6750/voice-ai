import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "@clerk/react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  CalendarDays,
  MessageCircle,
  Pencil,
  Phone,
  Unplug,
} from "lucide-react";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useResource } from "@/lib/resources";
import { CalendarIntegrationTestDialog } from "./CalendarIntegrationTestDialog";

type Provider = "whatsapp" | "twilio_voice";
type Section = "whatsapp" | "twilio" | "calendar";
type Connection = {
  id: string;
  label: string;
  provider: Provider;
  enabled: boolean;
  config: Record<string, unknown>;
  secret_names: string[];
  credential_id?: string | null;
  deleted_at?: string | null;
};
type CalendarIntegration = {
  id: string;
  display_name: string;
  provider: "google_calendar";
  calendar_id: string;
  timezone: string;
  status: string;
  connected_at?: string | null;
  last_error?: string | null;
};

const navigation = [
  {
    section: "whatsapp" as const,
    label: "WhatsApp",
    href: "/integrations/whatsapp",
    icon: MessageCircle,
  },
  {
    section: "twilio" as const,
    label: "Twilio Voice",
    href: "/integrations/twilio",
    icon: Phone,
  },
  {
    section: "calendar" as const,
    label: "Calendar",
    href: "/integrations/calendar",
    icon: CalendarDays,
  },
];

export function WhatsAppIntegrationsPage() {
  return <ProviderIntegrationsPage section="whatsapp" />;
}
export function TwilioIntegrationsPage() {
  return <ProviderIntegrationsPage section="twilio" />;
}
export function CalendarIntegrationsPage() {
  return <ProviderIntegrationsPage section="calendar" />;
}

function ProviderIntegrationsPage({ section }: { section: Section }) {
  const api = useApi();
  const { orgId } = useAuth();
  const navigate = useNavigate();
  const connections = useResource<{ connections: Connection[] }>(
    "/integrations",
  );
  const calendars = useResource<{ integrations: CalendarIntegration[] }>(
    "/calendar-integrations",
    section === "calendar",
  );
  const provider: Provider = section === "twilio" ? "twilio_voice" : "whatsapp";
  const isCalendar = section === "calendar";
  const title = isCalendar
    ? "Calendar"
    : section === "twilio"
      ? "Twilio Voice"
      : "WhatsApp";
  const description = isCalendar
    ? "Google Calendar connections used to check availability and schedule callbacks."
    : section === "twilio"
      ? "Manage the Twilio accounts and phone numbers used for voice calls."
      : "Manage your Meta WhatsApp connection, message templates, and media.";

  const [sheetOpen, setSheetOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [accountSid, setAccountSid] = useState("");
  const [phoneId, setPhoneId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [apiVersion, setApiVersion] = useState("v23.0");
  const [twilioCredentials, setTwilioCredentials] = useState<
    components["schemas"]["CredentialStatus"][]
  >([]);
  const [whatsappCredentials, setWhatsappCredentials] = useState<
    components["schemas"]["CredentialStatus"][]
  >([]);
  const [credentialId, setCredentialId] = useState("");
  const [calendarLabel, setCalendarLabel] = useState("My Google Calendar");
  const [reconnectingCalendarId, setReconnectingCalendarId] = useState<
    string | null
  >(null);
  const [renameTarget, setRenameTarget] = useState<CalendarIntegration | null>(
    null,
  );
  const [renameValue, setRenameValue] = useState("");
  const [disconnectTarget, setDisconnectTarget] =
    useState<CalendarIntegration | null>(null);
  const [calendarBusy, setCalendarBusy] = useState(false);

  useEffect(() => {
    let active = true;
    if (!orgId || isCalendar)
      return () => {
        active = false;
      };
    void api<components["schemas"]["CredentialStatus"][]>(
      `/orgs/${orgId}/credentials`,
    )
      .then((rows) => {
        if (!active) return;
        setTwilioCredentials(
          rows.filter(
            (row) => row.provider === "twilio" && row.status === "stored",
          ),
        );
        setWhatsappCredentials(
          rows.filter(
            (row) => row.provider === "whatsapp" && row.status === "stored",
          ),
        );
      })
      .catch(() => {
        if (active) {
          setTwilioCredentials([]);
          setWhatsappCredentials([]);
        }
      });
    return () => {
      active = false;
    };
  }, [api, orgId, isCalendar]);

  const providerConnections = (connections.data?.connections ?? []).filter(
    (item) => item.provider === provider,
  );
  const activeConnections = providerConnections.filter(
    (item) => !item.deleted_at,
  );
  const disconnectedConnections = providerConnections.filter((item) =>
    Boolean(item.deleted_at),
  );
  const activeCalendars = (calendars.data?.integrations ?? []).filter(
    (item) => item.status === "connected",
  );
  const disconnectedCalendars = (calendars.data?.integrations ?? []).filter(
    (item) => item.status !== "connected",
  );
  const hasActiveWhatsapp =
    section === "whatsapp" && activeConnections.length > 0;

  async function connectCalendar() {
    try {
      const result = await api<{ authorization_url: string }>(
        "/calendar-integrations/google/connect",
        {
          method: "POST",
          body: JSON.stringify({
            display_name: calendarLabel.trim() || "My Google Calendar",
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          }),
        },
      );
      window.location.assign(result.authorization_url);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not connect calendar",
      );
    }
  }

  async function reconnectCalendar(calendar: CalendarIntegration) {
    if (reconnectingCalendarId) return;
    setReconnectingCalendarId(calendar.id);
    try {
      const result = await api<{ authorization_url: string }>(
        `/calendar-integrations/${calendar.id}/reconnect`,
        { method: "POST" },
      );
      window.location.assign(result.authorization_url);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not reconnect calendar",
      );
      setReconnectingCalendarId(null);
    }
  }

  async function saveCalendarName() {
    const calendar = renameTarget;
    const displayName = renameValue.trim();
    if (!calendar || !displayName || displayName === calendar.display_name) {
      setRenameTarget(null);
      return;
    }
    try {
      setCalendarBusy(true);
      await api(`/calendar-integrations/${calendar.id}`, {
        method: "PATCH",
        body: JSON.stringify({ display_name: displayName }),
      });
      toast.success("Calendar name updated");
      await calendars.reload();
      setRenameTarget(null);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not rename calendar",
      );
    } finally {
      setCalendarBusy(false);
    }
  }

  async function confirmDisconnectCalendar() {
    const calendar = disconnectTarget;
    if (!calendar) return;
    try {
      setCalendarBusy(true);
      await api(`/calendar-integrations/${calendar.id}`, { method: "DELETE" });
      await calendars.reload();
      toast.success("Calendar disconnected");
      setDisconnectTarget(null);
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not disconnect calendar",
      );
    } finally {
      setCalendarBusy(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload =
        section === "twilio"
          ? {
              label: label.trim(),
              provider: "twilio_voice",
              enabled: false,
              credential_id: credentialId,
              config: { account_sid: accountSid.trim(), phone_numbers: [] },
            }
          : {
              label: label.trim(),
              provider: "whatsapp",
              enabled: false,
              credential_id: credentialId,
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

      if (section === "twilio" && credentialId) {
        try {
          const test = await api<{
            status: "ok" | "warning";
            message?: string;
          }>(`/integrations/${result.id}/test`, { method: "POST" });
          if (test.status === "ok") {
            const synced = await api<{ phone_numbers: unknown[] }>(
              `/integrations/${result.id}/refresh-numbers`,
              { method: "POST" },
            );
            await api<Connection>(`/integrations/${result.id}`, {
              method: "PATCH",
              body: JSON.stringify({ enabled: true }),
            });
            toast.success(
              `Twilio Voice connected (${synced.phone_numbers.length} voice numbers found)`,
            );
          } else {
            toast.warning(
              `Connection created but remains disabled. ${test.message || "This account is not ready for voice calls."}`,
              { duration: 8000 },
            );
          }
        } catch (cause) {
          toast.error(
            `Connection created but remains disabled: ${cause instanceof Error ? cause.message : "verification failed"}`,
            { duration: 8000 },
          );
        }
      } else {
        toast.success(
          "WhatsApp connection created and disabled until credentials are verified",
        );
      }
      setSheetOpen(false);
      setLabel("");
      setAccountSid("");
      setPhoneId("");
      setWabaId("");
      setCredentialId("");
      await connections.reload();
      navigate(`/integrations/${result.id}`);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not create connection",
      );
    } finally {
      setBusy(false);
    }
  }

  const action: ReactNode = isCalendar ? null : (
    <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
      <SheetTrigger asChild>
        <Button>
          {section === "twilio" ? "Add Twilio account" : "Connect WhatsApp"}
        </Button>
      </SheetTrigger>
      <SheetContent>
        <form
          onSubmit={create}
          className="flex h-full flex-col gap-6 overflow-y-auto"
        >
          <SheetHeader>
            <SheetTitle>
              {section === "twilio" ? "Add Twilio Voice" : "Connect WhatsApp"}
            </SheetTitle>
            <SheetDescription>
              {section === "twilio"
                ? "Link an organization credential and verify the account before enabling calling."
                : "Link a Meta credential to your WhatsApp Business phone number."}
            </SheetDescription>
          </SheetHeader>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="connection-label">
                Connection name
              </FieldLabel>
              <Input
                id="connection-label"
                placeholder={
                  section === "twilio" ? "Primary Twilio" : "Support WhatsApp"
                }
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                required
              />
            </Field>
            {section === "twilio" ? (
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
                    Must match the selected Twilio credential.
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="provider-credential">
                    Twilio credential
                  </FieldLabel>
                  <NativeSelect
                    id="provider-credential"
                    value={credentialId}
                    required
                    onChange={(event) => setCredentialId(event.target.value)}
                  >
                    <option value="">Select an organization credential</option>
                    {twilioCredentials.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · v{item.version}
                      </option>
                    ))}
                  </NativeSelect>
                  <FieldDescription>
                    {twilioCredentials.length
                      ? "Credentials are managed in Organization settings."
                      : "Add a Twilio credential in Organization settings first."}
                  </FieldDescription>
                </Field>
              </>
            ) : (
              <>
                <Field>
                  <FieldLabel htmlFor="provider-credential">
                    WhatsApp credential
                  </FieldLabel>
                  <NativeSelect
                    id="provider-credential"
                    value={credentialId}
                    required
                    onChange={(event) => setCredentialId(event.target.value)}
                  >
                    <option value="">Select an organization credential</option>
                    {whatsappCredentials.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} · v{item.version}
                      </option>
                    ))}
                  </NativeSelect>
                  <FieldDescription>
                    {whatsappCredentials.length
                      ? "Credentials are managed in Organization settings."
                      : "Add a Meta WhatsApp credential in Organization settings first."}
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
                  <FieldLabel htmlFor="wa-waba-id">
                    WhatsApp Business Account ID
                  </FieldLabel>
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
                    Meta Graph API version
                  </FieldLabel>
                  <Input
                    id="wa-api-version"
                    placeholder="v23.0"
                    pattern="^v[0-9]+\.0$"
                    value={apiVersion}
                    onChange={(event) => setApiVersion(event.target.value)}
                    required
                  />
                </Field>
                {hasActiveWhatsapp && (
                  <Alert>
                    <AlertDescription>
                      An active WhatsApp connection already exists. Disconnect
                      it before creating another.
                    </AlertDescription>
                  </Alert>
                )}
              </>
            )}
          </FieldGroup>
          <SheetFooter>
            <Button
              type="submit"
              disabled={busy || (section === "whatsapp" && hasActiveWhatsapp)}
            >
              {busy ? "Creating…" : "Create connection"}
            </Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );

  return (
    <PageBody>
      <PageHeader title={title} description={description} action={action} />
      <nav
        aria-label="Integration providers"
        className="flex max-w-full gap-1 overflow-x-auto border-b"
      >
        {navigation.map(({ section: itemSection, label, href, icon: Icon }) => (
          <Link
            key={itemSection}
            to={href}
            aria-current={section === itemSection ? "page" : undefined}
            className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-sm transition-colors ${section === itemSection ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            <Icon className="size-4" />
            {label}
          </Link>
        ))}
      </nav>

      {isCalendar ? (
        <div className="space-y-8">
          <section className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="font-semibold">Connected calendars</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Used by callback scheduling. Calendar access tokens remain on
                the server.
              </p>
            </div>
            <div className="flex w-full gap-2 sm:max-w-md">
              <Input
                aria-label="Calendar connection name"
                value={calendarLabel}
                onChange={(event) => setCalendarLabel(event.target.value)}
                placeholder="e.g. Sales team calendar"
              />
              <Button
                className="shrink-0"
                onClick={() => void connectCalendar()}
              >
                Connect Google
              </Button>
            </div>
          </section>
          <LoadState
            loading={calendars.loading}
            error={calendars.error}
            empty={
              activeCalendars.length === 0
                ? "No connected calendars. Connect Google Calendar to enable callback scheduling."
                : undefined
            }
          >
            <CalendarList
              calendars={activeCalendars}
              onRename={(calendar) => {
                setRenameTarget(calendar);
                setRenameValue(calendar.display_name);
              }}
              onDisconnect={setDisconnectTarget}
              onReconnect={reconnectCalendar}
              reconnectingCalendarId={reconnectingCalendarId}
              connected
            />
          </LoadState>
          {disconnectedCalendars.length > 0 && (
            <section className="space-y-3">
              <div className="border-b pb-3">
                <h2 className="text-sm font-semibold">
                  Disconnected calendars{" "}
                  <span className="ml-1 font-normal text-muted-foreground">
                    {disconnectedCalendars.length}
                  </span>
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  These connections are disconnected but kept so saved callback
                  assignments retain their calendar reference.
                </p>
              </div>
              <CalendarList
                calendars={disconnectedCalendars}
                onRename={(calendar) => {
                  setRenameTarget(calendar);
                  setRenameValue(calendar.display_name);
                }}
                onDisconnect={setDisconnectTarget}
                onReconnect={reconnectCalendar}
                reconnectingCalendarId={reconnectingCalendarId}
                connected={false}
              />
            </section>
          )}
        </div>
      ) : (
        <div className="space-y-8">
          <section className="space-y-3">
            <div className="flex items-end justify-between gap-4 border-b pb-3">
              <div>
                <h2 className="font-semibold">
                  {section === "twilio"
                    ? "Twilio accounts"
                    : "WhatsApp connections"}
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {section === "twilio"
                    ? "Verified accounts are enabled for voice calling."
                    : "Manage the active Meta Business connection and its messaging assets."}
                </p>
              </div>
              <span className="text-sm text-muted-foreground">
                {activeConnections.length} active
              </span>
            </div>
            <LoadState
              loading={connections.loading}
              error={connections.error}
              empty={
                activeConnections.length === 0
                  ? section === "twilio"
                    ? "No Twilio Voice accounts connected."
                    : "No WhatsApp connection configured."
                  : undefined
              }
            >
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Connection</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead>Credential</TableHead>
                    <TableHead className="text-right">Manage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeConnections.map((connection) => (
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
                        {connection.credential_id
                          ? ([
                              ...twilioCredentials,
                              ...whatsappCredentials,
                            ].find(
                              (item) => item.id === connection.credential_id,
                            )?.name ?? "Organization credential linked")
                          : connection.secret_names.join(", ") || "None"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="link">
                          <Link to={`/integrations/${connection.id}`}>
                            Open settings
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </LoadState>
          </section>
          {disconnectedConnections.length > 0 && (
            <section className="space-y-3">
              <div className="border-b pb-3">
                <h2 className="text-sm font-semibold">
                  Disconnected connections{" "}
                  <span className="ml-1 font-normal text-muted-foreground">
                    {disconnectedConnections.length}
                  </span>
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Previous connections remain listed for reference.
                </p>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Connection</TableHead>
                    <TableHead>State</TableHead>
                    <TableHead className="text-right">Manage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {disconnectedConnections.map((connection) => (
                    <TableRow key={connection.id}>
                      <TableCell className="font-medium">
                        {connection.label}
                      </TableCell>
                      <TableCell>
                        <StatusBadge value="disconnected" />
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="link">
                          <Link to={`/integrations/${connection.id}`}>
                            Open settings
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </section>
          )}
        </div>
      )}
      <Button asChild variant="link" className="w-fit px-0">
        <Link to="/integrations">All integrations</Link>
      </Button>
      <Dialog
        open={Boolean(renameTarget)}
        onOpenChange={(open) => {
          if (!open && !calendarBusy) setRenameTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename calendar</DialogTitle>
            <DialogDescription>
              Update the label shown to operators and callback scheduling.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor="calendar-rename">Calendar name</FieldLabel>
            <Input
              id="calendar-rename"
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              maxLength={120}
              autoFocus
            />
          </Field>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameTarget(null)}
              disabled={calendarBusy}
            >
              Cancel
            </Button>
            <Button
              onClick={() => void saveCalendarName()}
              disabled={calendarBusy || !renameValue.trim()}
            >
              {calendarBusy ? "Saving…" : "Save name"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <AlertDialog
        open={Boolean(disconnectTarget)}
        onOpenChange={(open) => {
          if (!open && !calendarBusy) setDisconnectTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Disconnect this calendar?</AlertDialogTitle>
            <AlertDialogDescription>
              {disconnectTarget?.display_name} will move to Disconnected
              calendars. Saved callback assignments keep their reference to it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={calendarBusy}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={calendarBusy}
              onClick={(event) => {
                event.preventDefault();
                void confirmDisconnectCalendar();
              }}
            >
              {calendarBusy ? "Disconnecting…" : "Disconnect calendar"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageBody>
  );
}

function CalendarList({
  calendars,
  onRename,
  onDisconnect,
  onReconnect,
  reconnectingCalendarId,
  connected,
}: {
  calendars: CalendarIntegration[];
  onRename: (calendar: CalendarIntegration) => void;
  onDisconnect: (calendar: CalendarIntegration) => void;
  onReconnect: (calendar: CalendarIntegration) => void;
  reconnectingCalendarId: string | null;
  connected: boolean;
}) {
  return (
    <div className="divide-y border-y">
      {calendars.map((calendar) => (
        <div
          key={calendar.id}
          className="flex flex-wrap items-center gap-3 py-4"
        >
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{calendar.display_name}</p>
            <p className="mt-1 truncate text-xs text-muted-foreground">
              {calendar.calendar_id} · {calendar.timezone}
            </p>
            {calendar.last_error && (
              <p className="mt-1 text-xs text-destructive">
                {calendar.last_error}
              </p>
            )}
          </div>
          <StatusBadge value={calendar.status} />
          {connected && (
            <CalendarIntegrationTestDialog
              integrationId={calendar.id}
              integrationName={calendar.display_name}
              disabled={!connected}
            />
          )}
          <Button
            variant="outline"
            size="sm"
            aria-label={`Reconnect ${calendar.display_name}`}
            disabled={reconnectingCalendarId !== null}
            onClick={() => void onReconnect(calendar)}
          >
            {reconnectingCalendarId === calendar.id
              ? "Reconnecting…"
              : "Reconnect Google"}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Rename ${calendar.display_name}`}
            onClick={() => onRename(calendar)}
          >
            <Pencil className="size-4" />
          </Button>
          {connected && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Disconnect ${calendar.display_name}`}
              title="Disconnect calendar"
              onClick={() => onDisconnect(calendar)}
            >
              <Unplug className="size-4" />
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
