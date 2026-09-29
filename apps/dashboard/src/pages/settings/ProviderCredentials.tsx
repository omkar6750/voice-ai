import { Fragment, useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { OrganizationView } from "@/app/organizations";
import type { components } from "@/generated/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

type CredentialStatus = components["schemas"]["ProviderCredentialStatus"];
const providers = [
  ["sarvam", "Sarvam", "Speech recognition and speech synthesis"],
  ["groq", "Groq", "Voice agent and classifier language model"],
  ["gemini", "Google Gemini", "Voice agent, classifier, and knowledge search"],
  ["cartesia", "Cartesia", "Speech synthesis"],
  ["jev", "JEV", "Lead classification"],
] as const;

export function ProviderCredentials() {
  const api = useApi();
  const { orgId } = useAuth();
  const [role, setRole] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<CredentialStatus[]>([]);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const [organization, credentials] = await Promise.all([
        api<OrganizationView>(`/orgs/${orgId}`),
        api<CredentialStatus[]>(`/orgs/${orgId}/credentials`),
      ]);
      setRole(organization.role);
      setStatuses(credentials);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load provider key status");
    } finally {
      setLoading(false);
    }
  }, [api, orgId]);

  useEffect(() => { void reload(); }, [reload]);

  async function save(provider: string) {
    const apiKey = keys[provider]?.trim();
    if (!orgId || !apiKey) return;
    setSaving(provider);
    try {
      await api(`/orgs/${orgId}/credentials/${provider}`, {
        method: "PUT",
        body: JSON.stringify({ api_key: apiKey }),
      });
      setKeys((current) => ({ ...current, [provider]: "" }));
      toast.success("Provider key saved securely");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not save provider key");
    } finally {
      setSaving(null);
    }
  }

  async function remove(provider: string) {
    if (!orgId || !window.confirm("Remove this organization’s saved provider key?")) return;
    try {
      await api(`/orgs/${orgId}/credentials/${provider}`, { method: "DELETE" });
      toast.success("Saved provider key removed");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not remove provider key");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI provider keys</CardTitle>
        <CardDescription>Keys are encrypted in the database, never sent back to the dashboard, and only loaded for calls in this organization.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {loading && <p role="status" className="text-sm text-muted-foreground">Loading key status…</p>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {!loading && !error && providers.map(([provider, label, purpose], index) => {
          const status = statuses.find((item) => item.provider === provider);
          const admin = role === "org:admin";
          return <Fragment key={provider}>{index > 0 && <Separator />}<section className="flex flex-col gap-3">
            <div>
              <h3 className="font-medium">{label}</h3>
              <p className="text-sm text-muted-foreground">{purpose}</p>
              <p className="text-sm" role="status">
                {status?.configured ? status.source === "deployment" ? "Configured by the deployment" : "Organization key saved" : "Not configured"}
              </p>
            </div>
            {admin && <FieldGroup>
              <Field>
                <FieldLabel htmlFor={`provider-key-${provider}`}>{status?.configured ? "Replace API key" : "API key"}</FieldLabel>
                <Input
                  id={`provider-key-${provider}`}
                  type="password"
                  autoComplete="new-password"
                  maxLength={4096}
                  value={keys[provider] ?? ""}
                  onChange={(event) => setKeys((current) => ({ ...current, [provider]: event.target.value }))}
                />
                <FieldDescription>Leave blank to keep the current key. The value is cleared from this form after saving.</FieldDescription>
              </Field>
              <div className="flex flex-wrap gap-2">
                <Button disabled={!keys[provider]?.trim() || saving !== null} onClick={() => void save(provider)}>
                  {saving === provider ? "Saving…" : "Save key"}
                </Button>
                {status?.source === "organization" && <Button variant="outline" disabled={saving !== null} onClick={() => void remove(provider)}>Remove saved key</Button>}
              </div>
            </FieldGroup>}
          </section></Fragment>;
        })}
      </CardContent>
    </Card>
  );
}
