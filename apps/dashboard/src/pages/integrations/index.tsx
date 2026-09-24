import { useEffect, useState, type FormEvent } from "react";
import {
  CheckCircle2,
  Copy,
  ExternalLink,
  Key,
  Layers,
  Link2,
  Lock,
  MessageSquare,
  Plus,
  RefreshCw,
  RotateCw,
  Send,
  ShieldCheck,
} from "lucide-react";
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
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Field, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import type {
  CreateConnectionBody,
  IntegrationConnection,
  WhatsAppTemplateItem,
} from "@/types/api";

export function IntegrationsPage() {
  const api = useApi();
  const [integrations, setIntegrations] = useState<IntegrationConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [secretInputs, setSecretInputs] = useState<
    Record<string, { name: string; value: string }>
  >({});
  const [submittingSecret, setSubmittingSecret] = useState<string | null>(null);
  const [rotatingSecret, setRotatingSecret] = useState<string | null>(null);

  // Template inspection state
  const [templatesLoading, setTemplatesLoading] = useState<string | null>(null);
  const [templatesMap, setTemplatesMap] = useState<
    Record<string, WhatsAppTemplateItem[]>
  >({});

  // Add Connection Sheet
  const [openAddSheet, setOpenAddSheet] = useState(false);
  const [creating, setCreating] = useState(false);
  const [label, setLabel] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [apiVersion, setApiVersion] = useState("v23.0");
  const [enabled, setEnabled] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = await api<{ connections: IntegrationConnection[] }>(
        "/integrations",
      );
      setIntegrations(data.connections);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load integrations",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreateConnection(e: FormEvent) {
    e.preventDefault();
    if (!label.trim() || !phoneNumberId.trim() || !wabaId.trim()) {
      toast.error("Please fill in connection label, phone number ID, and WABA ID");
      return;
    }
    setCreating(true);
    try {
      const body: CreateConnectionBody = {
        label: label.trim(),
        provider: "whatsapp",
        config: {
          phone_number_id: phoneNumberId.trim(),
          waba_id: wabaId.trim(),
          api_version: apiVersion.trim() || "v23.0",
        },
        enabled: enabled,
      };

      await api("/integrations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      toast.success(`WhatsApp integration '${label}' created`);
      setOpenAddSheet(false);
      setLabel("");
      setPhoneNumberId("");
      setWabaId("");
      await load();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to create integration",
      );
    } finally {
      setCreating(false);
    }
  }

  async function saveSecret(connectionId: string) {
    const target = secretInputs[connectionId];
    if (!target || !target.name.trim() || !target.value.trim()) {
      toast.error("Select or enter a secret key and its value");
      return;
    }
    setSubmittingSecret(connectionId);
    try {
      await api(
        `/integrations/${connectionId}/secrets/${encodeURIComponent(target.name.trim())}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ value: target.value.trim() }),
        },
      );
      toast.success(`Secret '${target.name}' encrypted and saved in vault`);
      setSecretInputs((prev) => ({
        ...prev,
        [connectionId]: { name: "", value: "" },
      }));
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save secret");
    } finally {
      setSubmittingSecret(null);
    }
  }

  async function handleRotateSecrets(connectionId: string) {
    setRotatingSecret(connectionId);
    try {
      await api(`/integrations/${connectionId}/rotate-secrets`, {
        method: "POST",
      });
      toast.success("All integration credentials re-encrypted with active master key");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to rotate secrets");
    } finally {
      setRotatingSecret(null);
    }
  }

  async function fetchTemplates(connectionId: string) {
    setTemplatesLoading(connectionId);
    try {
      const res = await api<{ templates: WhatsAppTemplateItem[] }>(
        `/integrations/${connectionId}/templates`,
      );
      setTemplatesMap((prev) => ({
        ...prev,
        [connectionId]: res.templates,
      }));
      toast.success(`Loaded ${res.templates.length} WhatsApp templates from Meta`);
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : "Could not fetch Meta WhatsApp templates. Ensure access_token is set.",
      );
    } finally {
      setTemplatesLoading(null);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            Integrations & Secret Vault
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Meta WhatsApp Cloud API connections, write-only Fernet credential vault,
            and action templates.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
          <Sheet open={openAddSheet} onOpenChange={setOpenAddSheet}>
            <SheetTrigger asChild>
              <Button size="sm" className="gap-1.5 bg-primary text-primary-foreground">
                <Plus className="size-3.5" /> New WhatsApp Connection
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="flex flex-col p-6 w-full sm:max-w-md">
              <SheetHeader className="p-0 mb-4">
                <SheetTitle className="flex items-center gap-2 text-lg">
                  <MessageSquare className="size-5 text-emerald-600" />
                  Connect WhatsApp Cloud API
                </SheetTitle>
                <SheetDescription>
                  Configure a Meta WhatsApp Business account for sending post-call
                  follow-up templates and media.
                </SheetDescription>
              </SheetHeader>

              <form
                onSubmit={handleCreateConnection}
                className="flex flex-col gap-4 flex-1 justify-between"
              >
                <div className="flex flex-col gap-3.5">
                  <Field>
                    <FieldLabel htmlFor="conn-label">Connection Label</FieldLabel>
                    <Input
                      id="conn-label"
                      placeholder="e.g. Northstar Sales WhatsApp"
                      required
                      value={label}
                      onChange={(e) => setLabel(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="conn-phone-id">
                      Meta Phone Number ID
                    </FieldLabel>
                    <Input
                      id="conn-phone-id"
                      placeholder="e.g. 583920194827104"
                      required
                      className="font-mono text-xs"
                      value={phoneNumberId}
                      onChange={(e) => setPhoneNumberId(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="conn-waba-id">
                      WhatsApp Business Account ID (WABA ID)
                    </FieldLabel>
                    <Input
                      id="conn-waba-id"
                      placeholder="e.g. 847291048291039"
                      required
                      className="font-mono text-xs"
                      value={wabaId}
                      onChange={(e) => setWabaId(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="conn-api-ver">Graph API Version</FieldLabel>
                    <Input
                      id="conn-api-ver"
                      placeholder="v23.0"
                      className="font-mono text-xs"
                      value={apiVersion}
                      onChange={(e) => setApiVersion(e.target.value)}
                    />
                  </Field>

                  <div className="flex items-center gap-2 pt-2">
                    <input
                      id="conn-enabled"
                      type="checkbox"
                      checked={enabled}
                      onChange={(e) => setEnabled(e.target.checked)}
                      className="size-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <label
                      htmlFor="conn-enabled"
                      className="text-xs font-medium text-foreground cursor-pointer"
                    >
                      Enable connection immediately
                    </label>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setOpenAddSheet(false)}
                    disabled={creating}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={
                      creating ||
                      !label.trim() ||
                      !phoneNumberId.trim() ||
                      !wabaId.trim()
                    }
                  >
                    {creating ? <Spinner className="size-4 mr-1.5" /> : null}
                    Save Connection
                  </Button>
                </div>
              </form>
            </SheetContent>
          </Sheet>
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
              Connect your WhatsApp Cloud API account to send dynamic post-call
              catalogs and follow-up templates.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-5">
          {integrations.map((conn) => {
            const currentSecret = secretInputs[conn.id] || {
              name: "access_token",
              value: "",
            };
            const templates = templatesMap[conn.id];

            return (
              <Card key={conn.id} className="shadow-none">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="flex size-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200">
                        <MessageSquare className="size-4" />
                      </div>
                      <div>
                        <CardTitle className="text-sm font-semibold">
                          {conn.label}
                        </CardTitle>
                        <div className="flex flex-wrap items-center gap-2 text-xs font-mono text-muted-foreground mt-0.5">
                          <span>Phone ID: {conn.config.phone_number_id}</span>
                          <span>•</span>
                          <span>WABA ID: {conn.config.waba_id}</span>
                          <span>•</span>
                          <span>API: {conn.config.api_version}</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="outline"
                        size="xs"
                        title="Rotate secrets"
                        disabled={rotatingSecret === conn.id}
                        onClick={() => void handleRotateSecrets(conn.id)}
                      >
                        <RotateCw
                          className={`size-3 mr-1 ${
                            rotatingSecret === conn.id ? "animate-spin" : ""
                          }`}
                        />
                        Rotate Vault
                      </Button>
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
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  {/* Stored Secret Badges */}
                  <div>
                    <span className="text-[11px] font-medium text-muted-foreground block mb-1.5">
                      Stored Credentials (Write-Only Fernet Encrypted):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {conn.secret_names.length === 0 ? (
                        <span className="text-xs text-muted-foreground italic">
                          No secrets stored in vault yet. Set `access_token` below.
                        </span>
                      ) : (
                        conn.secret_names.map((s) => (
                          <Badge
                            key={s}
                            variant="outline"
                            className="font-mono text-[11px] bg-muted/60"
                          >
                            <Lock className="size-3 mr-1 text-emerald-600" />
                            {s}
                          </Badge>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Secret Input Form */}
                  <div className="rounded-md border p-3 bg-muted/20">
                    <span className="text-xs font-medium text-foreground block mb-2">
                      Submit / Update Secret in Vault
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      <select
                        className="h-8 rounded-md border bg-background px-2.5 text-xs font-mono"
                        value={currentSecret.name}
                        onChange={(e) =>
                          setSecretInputs((prev) => ({
                            ...prev,
                            [conn.id]: {
                              ...currentSecret,
                              name: e.target.value,
                            },
                          }))
                        }
                      >
                        <option value="access_token">access_token (Meta System Token)</option>
                        <option value="app_secret">app_secret (Meta App Secret)</option>
                        <option value="verify_token">verify_token (Webhook Token)</option>
                      </select>
                      <Input
                        type="password"
                        placeholder="Paste secret value..."
                        className="text-xs h-8 flex-1 min-w-[200px] font-mono"
                        value={currentSecret.value}
                        onChange={(e) =>
                          setSecretInputs((prev) => ({
                            ...prev,
                            [conn.id]: {
                              ...currentSecret,
                              value: e.target.value,
                            },
                          }))
                        }
                      />
                      <Button
                        size="sm"
                        className="text-xs h-8"
                        disabled={
                          submittingSecret === conn.id ||
                          !currentSecret.value.trim()
                        }
                        onClick={() => void saveSecret(conn.id)}
                      >
                        <Key className="size-3.5 mr-1" />
                        {submittingSecret === conn.id ? "Encrypting…" : "Save to Vault"}
                      </Button>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-2">
                      Plaintext secrets are encrypted immediately using server-side
                      AES-128-CBC/HMAC Fernet keys and never stored in plaintext or
                      echoed back to the browser.
                    </p>
                  </div>

                  {/* Templates & Tool Generator Section */}
                  <div className="rounded-md border p-3">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div>
                        <span className="text-xs font-semibold text-foreground">
                          Approved WhatsApp Templates
                        </span>
                        <p className="text-[11px] text-muted-foreground">
                          Query live template specifications from Meta to bind into agent tool actions.
                        </p>
                      </div>
                      <Button
                        variant="outline"
                        size="xs"
                        disabled={templatesLoading === conn.id}
                        onClick={() => void fetchTemplates(conn.id)}
                      >
                        {templatesLoading === conn.id ? (
                          <Spinner className="size-3 mr-1" />
                        ) : (
                          <RefreshCw className="size-3 mr-1" />
                        )}
                        Fetch Templates
                      </Button>
                    </div>

                    {templates && (
                      <div className="mt-3 flex flex-col gap-2">
                        {templates.length === 0 ? (
                          <div className="text-xs text-muted-foreground italic p-2 border rounded bg-muted/10">
                            No approved templates found in this WhatsApp Business Account.
                          </div>
                        ) : (
                          templates.map((tpl) => (
                            <div
                              key={`${tpl.name}-${tpl.language}`}
                              className="rounded border p-2.5 bg-muted/10 flex flex-col gap-1.5"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-mono text-xs font-semibold">
                                  {tpl.name}
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <Badge variant="outline" className="text-[10px] font-mono">
                                    lang: {tpl.language}
                                  </Badge>
                                  <Badge
                                    variant="outline"
                                    className={
                                      tpl.status === "APPROVED"
                                        ? "bg-emerald-50 text-emerald-700 text-[10px]"
                                        : "text-[10px]"
                                    }
                                  >
                                    {tpl.status}
                                  </Badge>
                                </div>
                              </div>
                              {tpl.components?.map((c, idx) => (
                                <div key={idx} className="text-[11px] text-muted-foreground font-mono">
                                  {c.type}: {c.text || c.format || "media header"}
                                </div>
                              ))}
                            </div>
                          ))
                        )}
                      </div>
                    )}
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
