import { useState, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { PhoneCall, PhoneForwarded } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";

interface AgentSummary {
  id: string;
  slug: string;
  name: string;
  active_version?: {
    id: string;
    version_number: number;
    prompt_summary?: string;
  } | null;
}

interface ContactSummary {
  id: string;
  first_name: string;
  last_name: string;
  phone_e164: string;
  company_name?: string;
}

interface EndpointSummary {
  id: string;
  name: string;
  transport_type: string;
  status: string;
}

export function QuickDialer() {
  const api = useApi();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [contacts, setContacts] = useState<ContactSummary[]>([]);
  const [endpoints, setEndpoints] = useState<EndpointSummary[]>([]);

  const [selectedContactId, setSelectedContactId] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [agentId, setAgentId] = useState("");
  const [endpointId, setEndpointId] = useState("");
  const [dispatch, setDispatch] = useState(true);

  useEffect(() => {
    if (!open) return;

    api<AgentSummary[]>("/agents")
      .then((data) => {
        setAgents(data);
        if (data.length > 0 && !agentId) {
          setAgentId(data[0].id);
        }
      })
      .catch(() => {});

    api<ContactSummary[]>("/contacts")
      .then((data) => setContacts(data))
      .catch(() => {});

    api<EndpointSummary[]>("/runtime-endpoints")
      .then((data) => {
        setEndpoints(data);
        if (data.length > 0 && !endpointId) {
          setEndpointId(data[0].id);
        }
      })
      .catch(() => {});
  }, [open, api]);

  function handleContactChange(cId: string) {
    setSelectedContactId(cId);
    if (cId) {
      const found = contacts.find((c) => c.id === cId);
      if (found) {
        setPhoneNumber(found.phone_e164);
      }
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!phoneNumber.trim() || !agentId) {
      toast.error("Please provide a phone number and select an agent.");
      return;
    }

    setBusy(true);
    try {
      const selectedAgent = agents.find((a) => a.id === agentId);
      const payload: Record<string, unknown> = {
        to_number: phoneNumber.trim(),
        agent_id: agentId,
        dispatch: dispatch,
      };

      if (selectedAgent?.active_version?.id) {
        payload.agent_version_id = selectedAgent.active_version.id;
      }
      if (selectedContactId) {
        payload.contact_id = selectedContactId;
      }
      if (endpointId) {
        payload.endpoint_id = endpointId;
      }

      const res = await api<{ id: string; run_id?: string; status: string }>(
        "/calls",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      toast.success(
        dispatch ? "Call initiated and dispatching" : "Call created in queue",
      );
      setOpen(false);
      setPhoneNumber("");
      setSelectedContactId("");

      if (res.run_id) {
        navigate(`/runs/${res.run_id}`);
      } else {
        navigate("/runs");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to launch call");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button size="sm" className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs">
          <PhoneCall className="size-3.5" />
          <span>Quick Dial</span>
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex flex-col p-6 w-full sm:max-w-md">
        <SheetHeader className="p-0 mb-4">
          <SheetTitle className="flex items-center gap-2 text-lg">
            <PhoneForwarded className="size-5 text-emerald-600" />
            Launch Voice Call
          </SheetTitle>
          <SheetDescription>
            Dispatch an outbound voice call session to an E.164 phone number via
            the SIM7600 modem.
          </SheetDescription>
        </SheetHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 flex-1 justify-between">
          <div className="flex flex-col gap-4">
            <Field>
              <FieldLabel htmlFor="dialer-contact">Select Existing Contact (Optional)</FieldLabel>
              <NativeSelect
                id="dialer-contact"
                value={selectedContactId}
                onChange={(e) => handleContactChange(e.target.value)}
              >
                <option value="">-- Enter number manually or pick contact --</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} ({c.phone_e164}) {c.company_name ? `• ${c.company_name}` : ""}
                  </option>
                ))}
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel htmlFor="dialer-phone">Destination Phone (E.164 format)</FieldLabel>
              <Input
                id="dialer-phone"
                placeholder="+919876543210"
                required
                value={phoneNumber}
                onChange={(e) => setPhoneNumber(e.target.value)}
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="dialer-agent">Voice Agent & Flow</FieldLabel>
              <NativeSelect
                id="dialer-agent"
                required
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
              >
                <option value="" disabled>Select an agent...</option>
                {agents.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name} (Active v{a.active_version?.version_number ?? 1})
                  </option>
                ))}
              </NativeSelect>
            </Field>

            <Field>
              <FieldLabel htmlFor="dialer-endpoint">Telephony Endpoint</FieldLabel>
              <NativeSelect
                id="dialer-endpoint"
                value={endpointId}
                onChange={(e) => setEndpointId(e.target.value)}
              >
                {endpoints.length === 0 && <option value="">Default SIM7600 USB Audio</option>}
                {endpoints.map((ep) => (
                  <option key={ep.id} value={ep.id}>
                    {ep.name} ({ep.status})
                  </option>
                ))}
              </NativeSelect>
            </Field>

            <div className="flex items-center gap-2 pt-2">
              <input
                id="dialer-dispatch"
                type="checkbox"
                checked={dispatch}
                onChange={(e) => setDispatch(e.target.checked)}
                className="size-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
              />
              <label htmlFor="dialer-dispatch" className="text-sm font-medium text-foreground cursor-pointer">
                Dispatch immediately to hardware
              </label>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-4 border-t">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={busy || !phoneNumber.trim()}
              className="bg-emerald-600 hover:bg-emerald-700 text-white min-w-28"
            >
              {busy ? (
                <>
                  <Spinner className="size-4 mr-2" />
                  Dialing...
                </>
              ) : (
                <>
                  <PhoneCall className="size-4 mr-2" />
                  Dispatch Call
                </>
              )}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
