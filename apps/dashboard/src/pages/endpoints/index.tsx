import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Plus,
  Radio,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { useResource } from "@/lib/resources";

type EndpointsResponse = components["schemas"]["RuntimeEndpointsResponse"];
type EndpointStatus = components["schemas"]["EndpointStatus"];
type EndpointProbeResponse = components["schemas"]["EndpointProbeResponse"];
type EndpointRecoveryResponse =
  components["schemas"]["EndpointRecoveryResponse"];

export function EndpointsPage() {
  const api = useApi();
  const { data, loading, error, reload } =
    useResource<EndpointsResponse>("/runtime-endpoints");
  const [probeStatuses, setProbeStatuses] = useState<
    Record<string, EndpointStatus>
  >({});
  const [monitoringIds, setMonitoringIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [probingEndpointId, setProbingEndpointId] = useState<string | null>(
    null,
  );
  const probesInFlight = useRef(new Set<string>());

  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerBusy, setRegisterBusy] = useState(false);
  const [recoverBusy, setRecoverBusy] = useState<string | null>(null);
  const [recoveryResults, setRecoveryResults] = useState<
    Record<string, EndpointRecoveryResponse>
  >({});

  // Form fields
  const [name, setName] = useState("");
  const [atPort, setAtPort] = useState("COM16");
  const [audioPort, setAudioPort] = useState("COM17");
  const [baudrate, setBaudrate] = useState("115200");

  const probeEndpoint = useCallback(
    async (endpointId: string, manual: boolean) => {
      if (probesInFlight.current.has(endpointId)) return false;
      probesInFlight.current.add(endpointId);
      if (manual) setProbingEndpointId(endpointId);
      try {
        const result = await api<EndpointProbeResponse>(
          `/runtime-endpoints/${endpointId}/probe`,
          { method: "POST" },
        );
        setProbeStatuses((current) => ({
          ...current,
          [endpointId]: result.status,
        }));
        if (!result.status.alive) {
          setMonitoringIds((current) => {
            const next = new Set(current);
            next.delete(endpointId);
            return next;
          });
          if (manual) {
            toast.error(
              result.status.last_error ??
                "The modem did not respond to its AT check.",
            );
          } else {
            toast.error(
              "The modem connection was lost. Monitoring has stopped.",
            );
          }
          return false;
        }
        if (manual) toast.success("Modem is online. Checking every 5 seconds.");
        return true;
      } catch (cause) {
        setMonitoringIds((current) => {
          const next = new Set(current);
          next.delete(endpointId);
          return next;
        });
        if (manual) {
          toast.error(
            cause instanceof Error
              ? cause.message
              : "Could not test modem connection",
          );
        } else {
          toast.error(
            "Modem monitoring stopped because the status request failed.",
          );
        }
        return false;
      } finally {
        probesInFlight.current.delete(endpointId);
        if (manual) setProbingEndpointId(null);
      }
    },
    [api],
  );

  useEffect(() => {
    if (monitoringIds.size === 0) return;
    const timer = window.setInterval(() => {
      for (const endpointId of monitoringIds)
        void probeEndpoint(endpointId, false);
    }, 5_000);
    return () => window.clearInterval(timer);
  }, [monitoringIds, probeEndpoint]);

  async function startMonitoring(endpointId: string) {
    const connected = await probeEndpoint(endpointId, true);
    if (connected) {
      setMonitoringIds((current) => new Set(current).add(endpointId));
    }
  }

  async function registerEndpoint(e: FormEvent) {
    e.preventDefault();
    if (atPort.trim() === audioPort.trim()) {
      toast.error("AT port and Audio port must differ");
      return;
    }
    setRegisterBusy(true);
    try {
      await api("/runtime-endpoints", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          config: {
            provider: "sim7600",
            at_port: atPort.trim(),
            audio_port: audioPort.trim(),
            baudrate: Number(baudrate) || 115200,
            sample_rates: [8000, 16000],
          },
        }),
      });
      toast.success("Runtime endpoint registered");
      setRegisterOpen(false);
      setName("");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Failed to register endpoint",
      );
    } finally {
      setRegisterBusy(false);
    }
  }

  async function recoverEndpoint(endpointId: string) {
    setRecoverBusy(endpointId);
    try {
      const result = await api<EndpointRecoveryResponse>(
        `/runtime-endpoints/${endpointId}/recover`,
        {
          method: "POST",
        },
      );
      setRecoveryResults((previous) => ({ ...previous, [endpointId]: result }));
      if (result.endpoint_status) {
        setProbeStatuses((previous) => ({
          ...previous,
          [endpointId]: result.endpoint_status!,
        }));
      }
      if (result.status === "blocked") toast.error(result.message);
      else toast.success(result.message);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Failed to recover endpoint",
      );
    } finally {
      setRecoverBusy(null);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title="Runtime Endpoints"
        description="Physical SIM7600 USB modem hardware endpoints. Manages dedicated AT command serial and PCM audio channels."
        action={
          <Sheet open={registerOpen} onOpenChange={setRegisterOpen}>
            <SheetTrigger asChild>
              <Button>
                <Plus className="mr-1.5 size-4" />
                Register Endpoint
              </Button>
            </SheetTrigger>
            <SheetContent>
              <form
                onSubmit={registerEndpoint}
                className="flex h-full flex-col gap-6"
              >
                <SheetHeader>
                  <SheetTitle>Register Hardware Endpoint</SheetTitle>
                  <SheetDescription>
                    Configure physical COM port bindings for a SIM7600 modem
                    device.
                  </SheetDescription>
                </SheetHeader>

                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="endpoint-name">
                      Endpoint identifier
                    </FieldLabel>
                    <Input
                      id="endpoint-name"
                      placeholder="e.g. sim7600-primary"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                    <FieldDescription>
                      Unique descriptive hardware tag
                    </FieldDescription>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="at-port">AT command port</FieldLabel>
                    <Input
                      id="at-port"
                      placeholder="e.g. COM16"
                      value={atPort}
                      onChange={(e) => setAtPort(e.target.value)}
                      required
                    />
                    <FieldDescription>
                      Serial port for modem control & dialing
                    </FieldDescription>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="audio-port">Audio PCM port</FieldLabel>
                    <Input
                      id="audio-port"
                      placeholder="e.g. COM17"
                      value={audioPort}
                      onChange={(e) => setAudioPort(e.target.value)}
                      required
                    />
                    <FieldDescription>
                      Dedicated bidirectional PCM audio port
                    </FieldDescription>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="baudrate">Baud rate</FieldLabel>
                    <Input
                      id="baudrate"
                      type="number"
                      value={baudrate}
                      onChange={(e) => setBaudrate(e.target.value)}
                      required
                    />
                    <FieldDescription>
                      Standard SIM7600 baud rate: 115200
                    </FieldDescription>
                  </Field>
                </FieldGroup>

                <SheetFooter className="mt-auto">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setRegisterOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={registerBusy}>
                    {registerBusy ? "Registering…" : "Save Endpoint"}
                  </Button>
                </SheetFooter>
              </form>
            </SheetContent>
          </Sheet>
        }
      />

      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.endpoints.length === 0
            ? "No hardware endpoints registered. Connect and register a modem to place calls."
            : undefined
        }
      >
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {data?.endpoints.map((ep) => {
            const status = probeStatuses[ep.id] ?? ep.status;
            const checkedAt = status.checked_at
              ? new Date(status.checked_at)
              : null;
            const signalDbm =
              status.rssi != null ? 2 * status.rssi - 113 : null;
            const monitoring = monitoringIds.has(ep.id);
            const probing = probingEndpointId === ep.id;
            const needsRecovery = ep.active_run_status === "uncertain";
            const simReady =
              status.sim_status_known === false ? null : status.sim_ready;
            const voiceRegistered =
              status.voice_registration_known === false
                ? null
                : status.voice_registered;
            const dataRegistered =
              status.data_registration_known === false
                ? null
                : status.data_registered;
            const stale =
              checkedAt !== null && Date.now() - checkedAt.getTime() >= 120_000;
            return (
              <Card key={ep.id} className="flex flex-col justify-between">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base font-semibold">
                      <Radio className="size-4 text-primary" />
                      {ep.name}
                    </CardTitle>
                    <Badge
                      variant={status.alive && !stale ? "default" : "secondary"}
                    >
                      {stale
                        ? "Status stale"
                        : status.alive
                          ? "Online"
                          : "Offline"}
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    Provider: {ep.config.provider} · AT: {ep.config.at_port} ·
                    Audio: {ep.config.audio_port}
                  </CardDescription>
                </CardHeader>

                <CardContent className="space-y-4 pb-4 text-sm">
                  <div className="rounded-md border bg-muted/30 p-3 space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">SIM Card:</span>
                      <span className="font-medium">
                        {simReady === true ? (
                          <span className="flex items-center gap-1 text-emerald-600">
                            <CheckCircle2 className="size-3" /> Ready
                          </span>
                        ) : simReady === false ? (
                          <span className="flex items-center gap-1 text-destructive">
                            <XCircle className="size-3" /> Not Ready
                          </span>
                        ) : (
                          "Unknown"
                        )}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Operator:</span>
                      <span className="font-medium">
                        {status.operator ?? "Unknown"}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Radio access:
                      </span>
                      <span className="font-medium">
                        {status.radio_access !== "unknown"
                          ? status.radio_access
                          : "Unknown"}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Voice network:
                      </span>
                      <span className="font-medium">
                        {voiceRegistered === true
                          ? "Registered"
                          : voiceRegistered === false
                            ? "Not registered"
                            : "Unknown"}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Data network:
                      </span>
                      <span className="font-medium">
                        {dataRegistered === true
                          ? status.packet_attached
                            ? "Registered · attached"
                            : "Registered · not attached"
                          : dataRegistered === false
                            ? "Not registered"
                            : "Unknown"}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Roaming:</span>
                      <span className="font-medium">
                        {status.roaming === true
                          ? "Yes"
                          : status.roaming === false
                            ? "No"
                            : "Unknown"}
                      </span>
                    </div>

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Signal (RSSI):
                      </span>
                      <span className="font-medium">
                        {status.rssi == null
                          ? "Unknown"
                          : `${status.rssi} / 31${signalDbm === null ? "" : ` (about ${signalDbm} dBm)`}`}
                      </span>
                    </div>

                    {status.signal_quality != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">
                          Signal quality:
                        </span>
                        <span className="font-medium">
                          {status.signal_quality} / 7 BER
                        </span>
                      </div>
                    )}

                    {status.band && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">Band:</span>
                        <span className="font-medium">{status.band}</span>
                      </div>
                    )}

                    {status.usb_audio_supported != null && (
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">
                          USB audio:
                        </span>
                        <span className="font-medium">
                          {status.usb_audio_supported
                            ? status.usb_audio_active
                              ? "Active"
                              : "Available"
                            : "Unsupported"}
                        </span>
                      </div>
                    )}

                    <div className="flex justify-between">
                      <span className="text-muted-foreground">
                        Telephony Ready:
                      </span>
                      <span className="font-medium">
                        {status.can_make_call ? "Ready to Dial" : "No"}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Lease Status:</span>
                    {ep.active_run_id ? (
                      <Badge variant="destructive" asChild>
                        <Link to={`/runs/${ep.active_run_id}`}>
                          {needsRecovery ? "Needs recovery" : "Occupied"} (Run #
                          {ep.active_run_id.slice(0, 8)})
                        </Link>
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-emerald-600">
                        Available
                      </Badge>
                    )}
                  </div>

                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">
                      {monitoring
                        ? "Monitoring every 5 seconds"
                        : checkedAt
                          ? `Checked ${checkedAt.toLocaleTimeString()}`
                          : "Not tested yet"}
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={
                        probing || monitoring || Boolean(ep.active_run_id)
                      }
                      onClick={() => void startMonitoring(ep.id)}
                    >
                      <RefreshCw
                        className={`mr-1.5 size-3.5 ${probing || monitoring ? "animate-spin" : ""}`}
                      />
                      {monitoring
                        ? "Monitoring"
                        : probing
                          ? "Testing…"
                          : ep.active_run_id
                            ? needsRecovery
                              ? "Recover before testing"
                              : "Modem in use"
                            : "Test connection"}
                    </Button>
                  </div>

                  {status.last_error && (
                    <p className="flex items-center gap-1 text-xs text-destructive">
                      <AlertTriangle className="size-3.5 shrink-0" />
                      {status.last_error}
                    </p>
                  )}
                </CardContent>

                <CardFooter className="flex-col items-stretch gap-3 border-t pt-3">
                  {recoveryResults[ep.id] && (
                    <p
                      role="status"
                      className={
                        recoveryResults[ep.id].status === "blocked"
                          ? "text-xs text-destructive"
                          : "text-xs text-muted-foreground"
                      }
                    >
                      {recoveryResults[ep.id].message}
                    </p>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    className="w-full text-xs"
                    disabled={recoverBusy === ep.id}
                    onClick={() => void recoverEndpoint(ep.id)}
                  >
                    <RefreshCw
                      className={`mr-1.5 size-3.5 ${
                        recoverBusy === ep.id ? "animate-spin" : ""
                      }`}
                    />
                    {recoverBusy === ep.id
                      ? "Recovering…"
                      : "Reconcile / Recover Lease"}
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
        </div>
      </LoadState>
    </PageBody>
  );
}
