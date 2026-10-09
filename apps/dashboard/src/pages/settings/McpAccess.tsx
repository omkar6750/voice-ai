import { useEffect, useRef, useState, type FormEvent } from "react";
import { useAuth } from "@clerk/react";
import { toast } from "sonner";
import { useApi, useSupportSession } from "@/app/api";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { components } from "@/generated/api";
import { SettingsNavigation } from "./SettingsNavigation";

type Token = components["schemas"]["TokenView"];
type Issued = components["schemas"]["TokenIssued"];

export function McpAccessPage() {
  const api = useApi();
  const { orgId } = useAuth();
  const support = useSupportSession();
  const currentScope = useRef<string | null>(null);
  currentScope.current = support ? null : orgId ?? null;
  const [tokens, setTokens] = useState<Token[]>([]);
  const [issued, setIssued] = useState<(Issued & { orgId: string }) | null>(null);
  const [name, setName] = useState("Codex");
  const [days, setDays] = useState<7 | 30 | 90>(30);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const base = `/orgs/${orgId}/mcp-tokens`;

  useEffect(() => {
    let active = true;
    setIssued(null);
    setTokens([]);
    setError(null);
    setLoading(true);
    if (!orgId || support) { setLoading(false); return; }
    void api<Token[]>(base).then((rows) => { if (active) setTokens(rows); })
      .catch((cause) => { if (active) setError(cause instanceof Error ? cause.message : "Could not load tokens"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [api, base, orgId, support]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!orgId || support) return;
    setBusy(true);
    setIssued(null);
    try {
      const result = await api<Issued>(base, { method: "POST", body: JSON.stringify({ name, days }) });
      if (currentScope.current !== orgId) return;
      setIssued({ ...result, orgId });
      setTokens((rows) => [result.metadata, ...rows]);
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not create token"); }
    finally { setBusy(false); }
  }

  async function revoke(token: Token) {
    setBusy(true);
    try {
      await api(`${base}/${token.id}`, { method: "DELETE" });
      if (currentScope.current !== orgId) return;
      setTokens((rows) => rows.map((row) => row.id === token.id ? { ...row, revoked_at: new Date().toISOString() } : row));
      if (issued?.metadata.id === token.id) setIssued(null);
      toast.success("MCP token revoked");
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Could not revoke token"); }
    finally { setBusy(false); }
  }

  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); toast.success("Copied"); }
    catch { toast.error("Clipboard access unavailable"); }
  }

  const visible = issued?.orgId === orgId ? issued : null;
  const setup = visible ? `$env:${visible.connection.env_var} = '${visible.token}'\n[Environment]::SetEnvironmentVariable('${visible.connection.env_var}', $env:${visible.connection.env_var}, 'User')\n${visible.connection.command}` : "";

  return <PageBody>
    <PageHeader title="MCP access" description="Connect Codex to this organization with your current dashboard permissions. Credential management stays in the dashboard." />
    <SettingsNavigation active="/settings/mcp" />
    {support ? <Alert><AlertTitle>Direct membership required</AlertTitle><AlertDescription>Leave platform support mode to manage your MCP tokens.</AlertDescription></Alert> :
    <LoadState loading={loading} error={error}>
      <form onSubmit={create} className="flex max-w-xl flex-col gap-4">
        <FieldGroup>
          <Field><FieldLabel htmlFor="mcp-name">Token name</FieldLabel><Input id="mcp-name" value={name} maxLength={80} required onChange={(event) => setName(event.target.value)} /></Field>
          <Field><FieldLabel htmlFor="mcp-days">Expires after</FieldLabel><NativeSelect id="mcp-days" value={days} onChange={(event) => setDays(Number(event.target.value) as 7 | 30 | 90)}><option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option></NativeSelect></Field>
        </FieldGroup>
        <Button type="submit" disabled={busy || !orgId}>{busy ? "Working…" : "Create MCP token"}</Button>
      </form>
      {visible && <Alert>
        <AlertTitle>Save your token now</AlertTitle>
        <AlertDescription className="flex flex-col gap-3">
          <p>This token is shown once. It expires on {new Date(visible.metadata.expires_at).toLocaleString()}.</p>
          <Input aria-label="New MCP token" readOnly type="password" value={visible.token} />
          <p>{visible.connection.environment} · {visible.connection.url}</p>
          <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={() => void copy(visible.token)}>Copy token</Button><Button variant="outline" onClick={() => void copy(visible.connection.command)}>Copy Codex command</Button><Button variant="outline" onClick={() => void copy(setup)}>Copy PowerShell setup</Button><Button variant="ghost" onClick={() => setIssued(null)}>Dismiss token</Button></div>
          <p>The PowerShell setup saves the token in your Windows user environment and registers the server. Restart Codex afterward. Keep the copied setup private.</p>
        </AlertDescription>
      </Alert>}
      <div className="flex flex-col gap-3">{tokens.map((token) => <div key={token.id} className="flex items-center justify-between gap-4 border-b py-3">
        <div><p>{token.name} · {token.environment}</p><p className="text-sm text-muted-foreground">{token.revoked_at ? "Revoked" : `Expires ${new Date(token.expires_at).toLocaleString()}`} · {token.last_used_at ? `Last used ${new Date(token.last_used_at).toLocaleString()}` : "Never used"}</p></div>
        <Button variant="outline" disabled={busy || Boolean(token.revoked_at)} onClick={() => void revoke(token)}>Revoke</Button>
      </div>)}</div>
    </LoadState>}
  </PageBody>;
}
