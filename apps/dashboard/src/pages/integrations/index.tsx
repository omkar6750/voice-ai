import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Key, Link2, Lock, MessageSquare, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

interface IntegrationItem {
  id: string;
  label: string;
  provider: string;
  config: any;
  enabled: boolean;
  secret_names: string[];
}

export function IntegrationsPage() {
  const api = useApi();
  const [integrations, setIntegrations] = useState<IntegrationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [secretInputs, setSecretInputs] = useState<Record<string, { name: string; value: string }>>({});
  const [submittingSecret, setSubmittingSecret] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await api<{ connections: IntegrationItem[] }>("/integrations");
      setIntegrations(data.connections);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load integrations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function saveSecret(connectionId: string) {
    const target = secretInputs[connectionId];
    if (!target || !target.name.trim() || !target.value.trim()) {
      toast.error("Enter both secret name and secret value");
      return;
    }
    setSubmittingSecret(connectionId);
    try {
      await api(`/integrations/${connectionId}/secrets/${encodeURIComponent(target.name.trim())}`, {
        method: "PUT",
        body: JSON.stringify({ secret: target.value.trim() }),
      });
      toast.success(`Secret '${target.name}' encrypted and saved in vault`);
      setSecretInputs((prev) => ({ ...prev, [connectionId]: { name: "", value: "" } }));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save secret");
    } finally {
      setSubmittingSecret(null);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Integrations & Secret Vault</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Meta WhatsApp Cloud API connections, write-only Fernet credential vault, and action webhooks.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <Card className="p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-28 w-full" />
        </Card>
      ) : integrations.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No integrations configured</EmptyTitle>
            <EmptyDescription>
              Connect your WhatsApp Cloud API account to send dynamic post-call catalogs and follow-up templates.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-5">
          {integrations.map((conn) => {
            const currentSecret = secretInputs[conn.id] || { name: "", value: "" };

            return (
              <Card key={conn.id} className="shadow-none">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex size-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200">
                        <MessageSquare className="size-4" />
                      </div>
                      <div>
                        <CardTitle className="text-sm font-semibold">{conn.label}</CardTitle>
                        <CardDescription className="text-xs font-mono">
                          Provider: {conn.provider} · ID: {conn.id}
                        </CardDescription>
                      </div>
                    </div>
                    <Badge
                      variant="outline"
                      className={
                        conn.enabled
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200 text-[11px]"
                          : "bg-secondary text-muted-foreground text-[11px]"
                      }
                    >
                      {conn.enabled ? "Active" : "Disabled"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  {/* Stored Secret Badges */}
                  <div>
                    <span className="text-[11px] font-medium text-muted-foreground block mb-1.5">
                      Vault Stored Secrets (Write-Only Fernet Encrypted):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {conn.secret_names.length === 0 ? (
                        <span className="text-xs text-muted-foreground italic">No secrets stored in vault yet.</span>
                      ) : (
                        conn.secret_names.map((s) => (
                          <Badge key={s} variant="outline" className="font-mono text-[11px] bg-muted/60">
                            <Lock className="size-3 mr-1 text-muted-foreground" />
                            {s}
                          </Badge>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Secret Input Form */}
                  <div className="rounded-md border p-3 bg-muted/20">
                    <span className="text-xs font-medium text-foreground block mb-2">
                      Submit New Vault Secret
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      <Input
                        placeholder="Secret key (e.g. access_token)"
                        className="text-xs h-8 max-w-xs font-mono"
                        value={currentSecret.name}
                        onChange={(e) =>
                          setSecretInputs((prev) => ({
                            ...prev,
                            [conn.id]: { ...currentSecret, name: e.target.value },
                          }))
                        }
                      />
                      <Input
                        type="password"
                        placeholder="Secret value"
                        className="text-xs h-8 max-w-sm font-mono"
                        value={currentSecret.value}
                        onChange={(e) =>
                          setSecretInputs((prev) => ({
                            ...prev,
                            [conn.id]: { ...currentSecret, value: e.target.value },
                          }))
                        }
                      />
                      <Button
                        size="sm"
                        className="text-xs h-8"
                        disabled={submittingSecret === conn.id}
                        onClick={() => void saveSecret(conn.id)}
                      >
                        <Key className="size-3.5 mr-1" />
                        {submittingSecret === conn.id ? "Saving…" : "Save to Vault"}
                      </Button>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-2">
                      Plaintext secrets are encrypted immediately using AES-128-CBC/HMAC Fernet keys and never sent back to the browser.
                    </p>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
