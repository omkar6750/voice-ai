import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertTriangle, CheckCircle2, Plus, Radio, RefreshCw, XCircle } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
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

type EndpointRecord = {
  id: string;
  name: string;
  config: {
    provider: string;
    at_port: string;
    audio_port: string;
    baudrate: number;
    sample_rates: number[];
  };
  active_run_id: string | null;
  status: {
    checked_at: string | null;
    alive: boolean;
    sim_ready: boolean | null;
    can_make_call: boolean | null;
    radio_access: string;
    rssi: number | null;
    usb_audio_active: boolean | null;
    last_error: string | null;
  };
  last_seen_at: string | null;
  updated_at: string | null;
};

type EndpointsResponse = {
  endpoints: EndpointRecord[];
};

export function EndpointsPage() {
  const api = useApi();
  const { data, loading, error, reload } =
    useResource<EndpointsResponse>("/runtime-endpoints");

  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerBusy, setRegisterBusy] = useState(false);
  const [recoverBusy, setRecoverBusy] = useState<string | null>(null);

  // Form fields
  const [name, setName] = useState("");
  const [atPort, setAtPort] = useState("COM16");
  const [audioPort, setAudioPort] = useState("COM17");
  const [baudrate, setBaudrate] = useState("115200");

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
      await api(`/runtime-endpoints/${endpointId}/recover`, {
        method: "POST",
      });
      toast.success("Lease recovery triggered");
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
              <form onSubmit={registerEndpoint} className="flex h-full flex-col gap-6">
                <SheetHeader>
                  <SheetTitle>Register Hardware Endpoint</SheetTitle>
                  <SheetDescription>
                    Configure physical COM port bindings for a SIM7600 modem device.
                  </SheetDescription>
                </SheetHeader>

                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="endpoint-name">Endpoint identifier</FieldLabel>
                    <Input
                      id="endpoint-name"
                      placeholder="e.g. sim7600-primary"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                    <FieldDescription>Unique descriptive hardware tag</FieldDescription>
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
                    <FieldDescription>Serial port for modem control & dialing</FieldDescription>
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
                    <FieldDescription>Dedicated bidirectional PCM audio port</FieldDescription>
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
                    <FieldDescription>Standard SIM7600 baud rate: 115200</FieldDescription>
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
          {data?.endpoints.map((ep) => (
            <Card key={ep.id} className="flex flex-col justify-between">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold">
                    <Radio className="size-4 text-primary" />
                    {ep.name}
                  </CardTitle>
                  <Badge variant={ep.status.alive ? "default" : "secondary"}>
                    {ep.status.alive ? "Alive" : "Offline"}
                  </Badge>
                </div>
                <CardDescription className="text-xs">
                  Provider: {ep.config.provider} · AT: {ep.config.at_port} · Audio: {ep.config.audio_port}
                </CardDescription>
              </CardHeader>

              <CardContent className="space-y-4 pb-4 text-sm">
                <div className="rounded-md border bg-muted/30 p-3 space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">SIM Card:</span>
                    <span className="font-medium">
                      {ep.status.sim_ready === true ? (
                        <span className="flex items-center gap-1 text-emerald-600">
                          <CheckCircle2 className="size-3" /> Ready
                        </span>
                      ) : ep.status.sim_ready === false ? (
                        <span className="flex items-center gap-1 text-destructive">
                          <XCircle className="size-3" /> Not Detected
                        </span>
                      ) : (
                        "Unknown"
                      )}
                    </span>
                  </div>

                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Radio Network:</span>
                    <span className="font-medium">
                      {ep.status.radio_access !== "unknown" ? ep.status.radio_access : "Standby"}
                    </span>
                  </div>

                  {ep.status.rssi !== null && (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Signal (RSSI):</span>
                      <span className="font-medium">{ep.status.rssi} dBm</span>
                    </div>
                  )}

                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Telephony Ready:</span>
                    <span className="font-medium">
                      {ep.status.can_make_call ? "Ready to Dial" : "No"}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Lease Status:</span>
                  {ep.active_run_id ? (
                    <Badge variant="destructive" asChild>
                      <Link to={`/runs/${ep.active_run_id}`}>
                        Occupied (Run #{ep.active_run_id.slice(0, 8)})
                      </Link>
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-emerald-600">
                      Available
                    </Badge>
                  )}
                </div>

                {ep.status.last_error && (
                  <p className="flex items-center gap-1 text-xs text-destructive">
                    <AlertTriangle className="size-3.5 shrink-0" />
                    {ep.status.last_error}
                  </p>
                )}
              </CardContent>

              <CardFooter className="border-t pt-3">
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
                  {recoverBusy === ep.id ? "Recovering…" : "Reconcile / Recover Lease"}
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      </LoadState>
    </PageBody>
  );
}
