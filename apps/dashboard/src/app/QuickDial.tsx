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
type Call = { id: string; run_id: string; status: string; target_snapshot: string };

export function QuickDial() {
  const api = useApi();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [queued, setQueued] = useState<Call[]>([]);
  const [contactId, setContactId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [endpointId, setEndpointId] = useState("");
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
    ]).then(([contactData, choices, calls]) => {
      if (cancelled) return;
      setContacts(contactData.contacts);
      setVersions(choices.agent_versions);
      setEndpoints(choices.endpoints);
      setQueued(calls.calls.filter((call) => call.status === "queued"));
    }).catch((error: unknown) => {
      if (!cancelled) toast.error(error instanceof Error ? error.message : "Could not load dial options");
    }).finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [api, open]);

  async function create(dispatch: boolean) {
    if (!contactId || !versionId || !endpointId) return;
    setBusy(true);
    try {
      const result = await api<{ run_id: string; status: string }>("/calls", {
        method: "POST",
        body: JSON.stringify({
          contact_id: contactId,
          agent_version_id: versionId,
          endpoint_id: endpointId,
          logging_override: logging === "inherit" ? null : logging === "enabled",
          dispatch,
        }),
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
  const ready = !!contactId && !!versionId && !!endpointId && !busy && !loading;
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="sm"><PhoneCall data-icon="inline-start" />Quick dial</Button>
      </SheetTrigger>
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
              <FieldLabel htmlFor="dial-endpoint">Modem endpoint</FieldLabel>
              <NativeSelect id="dial-endpoint" className="w-full" value={endpointId} onChange={(event) => setEndpointId(event.target.value)} disabled={loading || busy}>
                <option value="">Select endpoint</option>
                {endpoints.map((item) => <option key={item.id} value={item.id}>{item.name}{item.active_run_id ? " · occupied" : ""}</option>)}
              </NativeSelect>
              <FieldDescription>
                {selectedEndpoint ? `Saved PCM rates: ${selectedEndpoint.sample_rates.join(", ")} Hz. Live modem health is not checked here.` : "Endpoint is required for both dispatch and queue."}
              </FieldDescription>
            </Field>
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
          <Button disabled={!ready || !!selectedEndpoint?.active_run_id} onClick={() => void create(true)}>Dispatch call</Button>
          <Button variant="outline" disabled={!ready} onClick={() => void create(false)}>Queue instead</Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
