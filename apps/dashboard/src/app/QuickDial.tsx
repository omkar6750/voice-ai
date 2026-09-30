import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PhoneCall } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "./api";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import {
  Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader,
  SheetTitle, SheetTrigger,
} from "@/components/ui/sheet";

type Contact = { id: string; name: string; phone_number: string };
type Version = { id: string; agent_name: string; version: number };
type Endpoint = {
  id: string; name: string; sample_rates: number[]; active_run_id: string | null;
};
type TwilioNumber = {
  sid: string; phone_number: string; friendly_name?: string | null; voice: boolean;
};
type TwilioConnection = {
  id: string;
  label: string;
  provider: string;
  enabled: boolean;
  deleted_at?: string | null;
  config: {
    account_sid?: string;
    account_type?: string;
    phone_numbers?: TwilioNumber[];
  };
};
type Call = { id: string; run_id: string; status: string; target_snapshot: string };

type QuickDialProps = {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
};

export function QuickDial({ open: controlledOpen, onOpenChange, hideTrigger = false }: QuickDialProps = {}) {
  const api = useApi();
  const navigate = useNavigate();
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [twilioConnections, setTwilioConnections] = useState<TwilioConnection[]>([]);
  const [queued, setQueued] = useState<Call[]>([]);
  const [contactId, setContactId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [telephonyProvider, setTelephonyProvider] = useState<"sim7600" | "twilio">("sim7600");
  const [endpointId, setEndpointId] = useState("");
  const [twilioConnectionId, setTwilioConnectionId] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [logging, setLogging] = useState("inherit");
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api<{ contacts: Contact[] }>("/contacts"),
      api<{ agent_versions: Version[]; endpoints: Endpoint[] }>("/dial-options"),
      api<{ calls: Call[] }>("/calls"),
      api<{ connections: TwilioConnection[] }>("/integrations"),
    ]).then(([contactData, choices, calls, integrations]) => {
      if (cancelled) return;
      setContacts(contactData.contacts);
      setVersions(choices.agent_versions);
      setEndpoints(choices.endpoints);
      setQueued(calls.calls.filter((call) => call.status === "queued"));
      const activeTwilio = (integrations.connections || []).filter(
        (c) => c.provider === "twilio_voice" && !c.deleted_at && c.enabled
      );
      setTwilioConnections(activeTwilio);
      if (activeTwilio.length > 0 && telephonyProvider === "sim7600" && choices.endpoints.length === 0) {
        setTelephonyProvider("twilio");
        setTwilioConnectionId(activeTwilio[0].id);
      }
    }).catch((error: unknown) => {
      if (!cancelled) toast.error(error instanceof Error ? error.message : "Could not load dial options");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, open]);

  const selectedTwilio = twilioConnections.find((c) => c.id === twilioConnectionId);
  const availableNumbers = (selectedTwilio?.config?.phone_numbers || []).filter((n) => n.voice);
  const isTrial = selectedTwilio?.config?.account_type === "Trial";

  useEffect(() => {
    if (selectedTwilio && availableNumbers.length > 0 && !fromNumber) {
      setFromNumber(availableNumbers[0].phone_number);
    }
  }, [selectedTwilio, availableNumbers, fromNumber]);

  async function create(dispatch: boolean) {
    if (!contactId || !versionId) return;
    if (telephonyProvider === "sim7600" && !endpointId) return;
    if (telephonyProvider === "twilio" && (!twilioConnectionId || !fromNumber || isTrial)) return;

    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        contact_id: contactId,
        agent_version_id: versionId,
        logging_override: logging === "inherit" ? null : logging === "enabled",
        dispatch,
      };

      if (telephonyProvider === "twilio") {
        payload.telephony = {
          provider: "twilio",
          connection_id: twilioConnectionId,
          from_number: fromNumber,
        };
      } else {
        payload.endpoint_id = endpointId;
        payload.telephony = {
          provider: "sim7600",
          endpoint_id: endpointId,
        };
      }

      const result = await api<{ run_id: string; status: string }>("/calls", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      toast.success(dispatch ? "Call dispatch requested" : "Call queued");
      setOpen(false);
      navigate(`/runs/${result.run_id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Call request failed");
    } finally { setBusy(false); }
  }

  async function dispatch(call: Call) {
    setBusy(true);
    try {
      await api(`/calls/${call.id}/dispatch`, { method: "POST" });
      toast.success("Queued call dispatch requested");
      setOpen(false);
      navigate(`/runs/${call.run_id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Dispatch failed");
    } finally { setBusy(false); }
  }

  const selectedEndpoint = endpoints.find((item) => item.id === endpointId);
  const ready =
    !!contactId &&
    !!versionId &&
    (telephonyProvider === "twilio"
      ? !!twilioConnectionId && !!fromNumber && !isTrial
      : !!endpointId && !selectedEndpoint?.active_run_id) &&
    !busy &&
    !loading;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {!hideTrigger && <SheetTrigger asChild>
        <Button size="sm"><PhoneCall data-icon="inline-start" />Quick dial</Button>
      </SheetTrigger>}
      <SheetContent className="overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Quick dial</SheetTitle>
          <SheetDescription>Dispatch now or save a call request to dispatch later.</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-6 px-4">
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="dial-contact">Contact</FieldLabel>
              <NativeSelect id="dial-contact" className="w-full" value={contactId} onChange={(event) => setContactId(event.target.value)} disabled={loading || busy}>
                <option value="">Select contact</option>
                {contacts.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.phone_number}</option>)}
              </NativeSelect>
            </Field>
            <Field>
              <FieldLabel htmlFor="dial-version">Published agent version</FieldLabel>
              <NativeSelect id="dial-version" className="w-full" value={versionId} onChange={(event) => setVersionId(event.target.value)} disabled={loading || busy}>
                <option value="">Select version</option>
                {versions.map((item) => <option key={item.id} value={item.id}>{item.agent_name} · v{item.version}</option>)}
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel>Telephony provider</FieldLabel>
              <div className="flex items-center gap-4 py-1">
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="telephonyProvider"
                    value="twilio"
                    checked={telephonyProvider === "twilio"}
                    onChange={() => setTelephonyProvider("twilio")}
                    disabled={busy || twilioConnections.length === 0}
                  />
                  <span>Twilio Voice</span>
                </label>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    name="telephonyProvider"
                    value="sim7600"
                    checked={telephonyProvider === "sim7600"}
                    onChange={() => setTelephonyProvider("sim7600")}
                    disabled={busy}
                  />
                  <span>SIM7600 Modem</span>
                </label>
              </div>
              {twilioConnections.length === 0 && (
                <FieldDescription>
                  No enabled Twilio Voice connections found. Configure one in Integrations.
                </FieldDescription>
              )}
            </Field>

            {telephonyProvider === "twilio" ? (
              <>
                <Field>
                  <FieldLabel htmlFor="dial-twilio-conn">Twilio account</FieldLabel>
                  <NativeSelect
                    id="dial-twilio-conn"
                    className="w-full"
                    value={twilioConnectionId}
                    onChange={(e) => {
                      setTwilioConnectionId(e.target.value);
                      setFromNumber("");
                    }}
                    disabled={loading || busy}
                  >
                    <option value="">Select Twilio account</option>
                    {twilioConnections.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.label} ({c.config?.account_type || "Twilio"})
                      </option>
                    ))}
                  </NativeSelect>
                </Field>

                {isTrial && (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-md text-xs text-amber-600 dark:text-amber-400">
                    <strong>Trial Account:</strong> Twilio trial accounts disallow Media Streams. An upgraded account is required to place outbound calls.
                  </div>
                )}

                <Field>
                  <FieldLabel htmlFor="dial-from-number">From number</FieldLabel>
                  <NativeSelect
                    id="dial-from-number"
                    className="w-full"
                    value={fromNumber}
                    onChange={(e) => setFromNumber(e.target.value)}
                    disabled={loading || busy || !twilioConnectionId || isTrial}
                  >
                    <option value="">Select originating number</option>
                    {availableNumbers.map((n) => (
                      <option key={n.sid} value={n.phone_number}>
                        {n.phone_number} {n.friendly_name ? `(${n.friendly_name})` : ""}
                      </option>
                    ))}
                  </NativeSelect>
                  {twilioConnectionId && availableNumbers.length === 0 && (
                    <FieldDescription className="text-amber-500">
                      No voice-capable numbers synchronized for this account. Refresh numbers in Integrations.
                    </FieldDescription>
                  )}
                </Field>
              </>
            ) : (
              <Field>
                <FieldLabel htmlFor="dial-endpoint">Modem endpoint</FieldLabel>
                <NativeSelect id="dial-endpoint" className="w-full" value={endpointId} onChange={(event) => setEndpointId(event.target.value)} disabled={loading || busy}>
                  <option value="">Select endpoint</option>
                  {endpoints.map((item) => <option key={item.id} value={item.id}>{item.name}{item.active_run_id ? " · occupied" : ""}</option>)}
                </NativeSelect>
                <FieldDescription>
                  {selectedEndpoint ? `Saved PCM rates: ${selectedEndpoint.sample_rates.join(", ")} Hz. Live modem health is not checked here.` : "Endpoint is required for SIM7600."}
                </FieldDescription>
              </Field>
            )}

            <Field>
              <FieldLabel htmlFor="dial-logging">Pipeline logging</FieldLabel>
              <NativeSelect id="dial-logging" className="w-full" value={logging} onChange={(event) => setLogging(event.target.value)} disabled={busy}>
                <option value="inherit">Use agent/workspace setting</option>
                <option value="enabled">Enable for this call</option>
                <option value="disabled">Disable for this call</option>
              </NativeSelect>
            </Field>
          </FieldGroup>
          <Separator />
          <section className="flex flex-col gap-3">
            <h3 className="text-sm font-medium">Queued calls</h3>
            <p className="text-xs text-muted-foreground">Queueing does not auto-dial. Dispatch a request explicitly when ready.</p>
            {queued.length === 0 && <p className="text-sm text-muted-foreground">No queued calls.</p>}
            {queued.map((call) => (
              <div key={call.id} className="flex items-center justify-between gap-2 text-sm">
                <span>{call.target_snapshot}</span>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => void dispatch(call)}>Dispatch</Button>
              </div>
            ))}
          </section>
        </div>
        <SheetFooter>
          <Button disabled={!ready} onClick={() => void create(true)}>Dispatch call</Button>
          <Button variant="outline" disabled={!ready} onClick={() => void create(false)}>Queue instead</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
