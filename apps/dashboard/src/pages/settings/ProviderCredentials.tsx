import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { toast } from "sonner";
import { useOrganizationAccess } from "@/app/access";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import { useResource } from "@/lib/resources";

type Credential = components["schemas"]["CredentialStatus"];
type Provider = Credential["provider"];
type SecretFields = { name: string; api_key: string; account_sid: string; api_key_sid: string; api_key_secret: string; auth_token: string };
const emptyFields: SecretFields = { name: "", api_key: "", account_sid: "", api_key_sid: "", api_key_secret: "", auth_token: "" };
const providers: Array<{ id: Provider; label: string; purpose: string }> = [
  { id: "sarvam", label: "Sarvam", purpose: "Chat models, speech recognition and speech synthesis" },
  { id: "groq", label: "Groq", purpose: "Voice agent, classifier and summarizer" },
  { id: "openrouter", label: "OpenRouter", purpose: "Account-specific models for LLM, classifier and summarizer" },
  { id: "gemini", label: "Google Gemini", purpose: "Voice agent, classifier and knowledge search" },
  { id: "cartesia", label: "Cartesia", purpose: "Speech synthesis" },
  { id: "jev", label: "JEV", purpose: "Lead classification" },
  { id: "whatsapp", label: "WhatsApp Cloud", purpose: "Meta WhatsApp Cloud API access token" },
  { id: "twilio", label: "Twilio", purpose: "Account SID, REST API key and separate webhook Auth Token" },
];

export function ProviderCredentials() {
  const api = useApi();
  const { orgId } = useAuth();
  const { canManage } = useOrganizationAccess();
  const { data, loading, error, reload } = useResource<Credential[]>(
    orgId ? `/orgs/${orgId}/credentials` : "",
    Boolean(orgId),
  );
  const [fields, setFields] = useState<SecretFields>(emptyFields);
  const [provider, setProvider] = useState<Provider>("groq");
  const [replacement, setReplacement] = useState<Credential | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setFields(emptyFields); setReplacement(null); }, [orgId]);

  function begin(providerId: Provider, credential?: Credential) {
    setProvider(providerId);
    setReplacement(credential ?? null);
    setFields({ ...emptyFields, name: credential?.name ?? "" });
  }

  async function save() {
    if (!orgId || !fields.name.trim()) return;
    setSaving(true);
    try {
      const body = provider === "twilio"
        ? { ...fields, provider, ...(replacement ? { expected_version: replacement.version } : {}) }
        : { name: fields.name, provider, api_key: fields.api_key, ...(replacement ? { expected_version: replacement.version } : {}) };
      await api(replacement
        ? `/orgs/${orgId}/credentials/${replacement.id}`
        : `/orgs/${orgId}/credentials`, {
        method: replacement ? "PUT" : "POST",
        body: JSON.stringify(body),
      });
      toast.success(replacement ? "Credential replaced for future calls" : "Credential added securely");
      setReplacement(null);
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save credential");
    } finally {
      // Clear every secret after every attempt; no value survives an org switch or response.
      setFields(emptyFields);
      setSaving(false);
    }
  }

  async function rename(item: Credential) {
    if (!orgId) return;
    const name = window.prompt("New credential name", item.name)?.trim();
    if (!name || name === item.name) return;
    try {
      await api(`/orgs/${orgId}/credentials/${item.id}/name`, {
        method: "PATCH", body: JSON.stringify({ name, expected_version: item.version }),
      });
      await reload();
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not rename credential"); }
  }

  async function remove(item: Credential) {
    if (!orgId || !window.confirm(`Delete “${item.name}”? New calls will be blocked. This does not revoke the key with the vendor; revoke it there separately.`)) return;
    try {
      await api(`/orgs/${orgId}/credentials/${item.id}`, {
        method: "DELETE", body: JSON.stringify({ expected_version: item.version }),
      });
      toast.success("Credential removed from this application");
      await reload();
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not delete credential"); }
  }

  const admin = canManage;
  const statuses = data ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Provider credentials</CardTitle>
        <CardDescription>Named credentials are encrypted per organization and provider. Values are write-only. Deleting here does not revoke a vendor key or remove their historical backups.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {loading && <p role="status" className="text-sm text-muted-foreground">Loading credentials…</p>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {!loading && !error && providers.map((item, index) => {
          const rows = statuses.filter((status) => status.provider === item.id);
          return <section key={item.id} className="flex flex-col gap-3">
            {index > 0 && <Separator />}
            <div><h3 className="font-medium">{item.label}</h3><p className="text-sm text-muted-foreground">{item.purpose}</p></div>
            {rows.length === 0 && <p className="text-sm text-muted-foreground">No credentials added.</p>}
            {rows.map((row) => <div key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3">
              <div><p className="font-medium">{row.name}</p><p className="text-xs text-muted-foreground">{row.status} · version {row.version} · {row.id}</p></div>
              {admin && row.status !== "deleted" && <div className="flex gap-2">
                <Button variant="outline" onClick={() => begin(item.id, row)}>Replace</Button>
                <Button variant="outline" onClick={() => void rename(row)}>Rename</Button>
                <Button variant="destructive" onClick={() => void remove(row)}>Delete</Button>
              </div>}
            </div>)}
            {admin && <Button variant="outline" className="self-start" onClick={() => begin(item.id)}>Add {item.label} credential</Button>}
          </section>;
        })}
        {admin && <>
          <Separator />
          <section className="flex flex-col gap-4">
            <h3 className="font-medium">{replacement ? `Replace ${replacement.name}` : "Add a credential"}</h3>
            <FieldGroup>
              {!replacement && <Field><FieldLabel htmlFor="credential-provider">Provider</FieldLabel><NativeSelect id="credential-provider" value={provider} onChange={(event) => { setProvider(event.target.value as Provider); setFields(emptyFields); }}>
                {providers.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </NativeSelect></Field>}
              <Field><FieldLabel htmlFor="credential-name">Name</FieldLabel><Input id="credential-name" maxLength={120} value={fields.name} onChange={(event) => setFields({ ...fields, name: event.target.value })} /></Field>
              {provider === "twilio" ? <>
                <SecretInput id="twilio-account-sid" label="Twilio Account SID" value={fields.account_sid} onChange={(value) => setFields({ ...fields, account_sid: value })} />
                <SecretInput id="twilio-api-sid" label="Twilio API Key SID" value={fields.api_key_sid} onChange={(value) => setFields({ ...fields, api_key_sid: value })} />
                <SecretInput id="twilio-api-secret" label="Twilio API Key Secret (REST)" value={fields.api_key_secret} onChange={(value) => setFields({ ...fields, api_key_secret: value })} />
                <SecretInput id="twilio-auth-token" label="Twilio Auth Token (webhook signature)" value={fields.auth_token} onChange={(value) => setFields({ ...fields, auth_token: value })} />
              </> : <SecretInput id="provider-api-key" label={provider === "whatsapp" ? "WhatsApp Cloud access token" : "API key"} value={fields.api_key} onChange={(value) => setFields({ ...fields, api_key: value })} />}
              <FieldDescription>Secrets are sent only to the authenticated API, never returned or saved in browser storage.</FieldDescription>
              <div className="flex gap-2"><Button disabled={saving || !fields.name.trim()} onClick={() => void save()}>{saving ? "Saving…" : replacement ? "Replace for future calls" : "Save credential"}</Button><Button variant="outline" disabled={saving} onClick={() => { setReplacement(null); setFields(emptyFields); }}>Clear form</Button></div>
            </FieldGroup>
          </section>
        </>}
      </CardContent>
    </Card>
  );
}

function SecretInput({ id, label, value, onChange }: { id: string; label: string; value: string; onChange: (value: string) => void }) {
  return <Field><FieldLabel htmlFor={id}>{label}</FieldLabel><Input id={id} type="password" autoComplete="new-password" maxLength={4096} value={value} onChange={(event) => onChange(event.target.value)} /></Field>;
}
