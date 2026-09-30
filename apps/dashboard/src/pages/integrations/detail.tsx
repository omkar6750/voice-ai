import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@clerk/react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  PowerOff,
  Trash2,
  ExternalLink,
  Pencil,
  Phone,
  RefreshCw,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import type { components } from "@/generated/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  LoadState,
  PageBody,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
} from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
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
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useResource } from "@/lib/resources";
import { MediaPanel } from "./MediaPanel";
import { WhatsAppMediaPicker } from "./WhatsAppMediaPicker";
import type { Connection } from "./index";

type TemplateComponent = {
  type: string;
  text?: string;
  format?: string;
};

type Media = components["schemas"]["MediaResponse"];

type Template = {
  name: string;
  status?: string;
  language?: string;
  category?: string;
  components?: TemplateComponent[];
};

function templateParameterNames(template: Template | null): string[] {
  const body = template?.components?.find((item) => item.type === "BODY");
  const matches = [...(body?.text?.matchAll(/\{\{(\d+)\}\}/g) ?? [])];
  const indexes = [...new Set(matches.map((match) => match[1]))];
  if (indexes.length > 1) {
    return indexes.map((index) =>
      index === "1" ? "caller_name" : `param_${index}`,
    );
  }
  return indexes.length === 1 ? ["message"] : [];
}

function templateParameterMappings(
  template: Template | null,
): Record<string, string> {
  const body = template?.components?.find((item) => item.type === "BODY");
  const indexes = [
    ...new Set(
      [...(body?.text?.matchAll(/\{\{(\d+)\}\}/g) ?? [])].map(
        (match) => match[1],
      ),
    ),
  ];
  if (indexes.length === 1) return { [indexes[0]]: "message" };
  return Object.fromEntries(
    indexes.map((index) => [
      index,
      index === "1" ? "caller_name" : `param_${index}`,
    ]),
  );
}

const whatsappSections = ["Account", "Media", "Templates"] as const;
const twilioSections = ["Account", "Phone Numbers"] as const;

export function IntegrationDetailPage() {
  const { connectionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const api = useApi();
  const { orgId } = useAuth();
  const { canManage } = useOrganizationAccess();
  const navigate = useNavigate();
  const {
    data: connection,
    loading,
    error,
    reload,
  } = useResource<Connection>(`/integrations/${connectionId}`);

  const isTwilio = connection?.provider === "twilio_voice";
  const sections = isTwilio ? twilioSections : whatsappSections;

  const section =
    sections.find(
      (item) => item.toLowerCase() === params.get("section")?.toLowerCase(),
    ) ?? "Account";

  // Account editing state
  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [phoneId, setPhoneId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [accountSid, setAccountSid] = useState("");
  const [credentialId, setCredentialId] = useState("");
  const [webhookSecretValues, setWebhookSecretValues] = useState({
    app_secret: "",
    verify_token: "",
  });
  const [savingWebhookSecret, setSavingWebhookSecret] = useState<
    "app_secret" | "verify_token" | null
  >(null);
  const [twilioCredentials, setTwilioCredentials] = useState<components["schemas"]["CredentialStatus"][]>([]);
  const [whatsappCredentials, setWhatsappCredentials] = useState<components["schemas"]["CredentialStatus"][]>([]);
  const [linkedCredential, setLinkedCredential] = useState<components["schemas"]["CredentialStatus"] | null>(null);
  const [linkedCredentialLoading, setLinkedCredentialLoading] = useState(false);
  const [linkedCredentialUnavailable, setLinkedCredentialUnavailable] = useState(false);

  useEffect(() => {
    let active = true;
    if (!orgId) { setTwilioCredentials([]); setWhatsappCredentials([]); return () => { active = false; }; }
    void api<components["schemas"]["CredentialStatus"][]>(`/orgs/${orgId}/credentials`)
      .then((rows) => { if (active) {
        setTwilioCredentials(rows.filter((row) => row.provider === "twilio"));
        setWhatsappCredentials(rows.filter((row) => row.provider === "whatsapp"));
      } })
      .catch(() => { if (active) { setTwilioCredentials([]); setWhatsappCredentials([]); } });
    return () => { active = false; };
  }, [api, orgId]);

  useEffect(() => {
    let active = true;
    const credentialId = connection?.credential_id;
    if (!orgId || !credentialId) {
      setLinkedCredential(null);
      setLinkedCredentialLoading(false);
      setLinkedCredentialUnavailable(false);
      return () => { active = false; };
    }
    setLinkedCredentialLoading(true);
    setLinkedCredentialUnavailable(false);
    void api<components["schemas"]["CredentialStatus"]>(
      `/orgs/${orgId}/credentials/${credentialId}`,
    )
      .then((row) => { if (active) setLinkedCredential(row); })
      .catch(() => { if (active) setLinkedCredentialUnavailable(true); })
      .finally(() => { if (active) setLinkedCredentialLoading(false); });
    return () => { active = false; };
  }, [api, connection?.credential_id, orgId]);

  const selectedCredential = linkedCredential?.id === connection?.credential_id
    ? linkedCredential
    : (isTwilio ? twilioCredentials : whatsappCredentials).find(
        (item) => item.id === connection?.credential_id,
      );
  const compatibleCredentials = isTwilio ? twilioCredentials : whatsappCredentials;

  useEffect(() => {
    setWebhookSecretValues({ app_secret: "", verify_token: "" });
  }, [connectionId, orgId]);

  async function saveWebhookSecret(name: "app_secret" | "verify_token") {
    const value = webhookSecretValues[name];
    if (!value) return;
    setSavingWebhookSecret(name);
    try {
      await api(`/integrations/${connectionId}/secrets/${name}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      });
      toast.success(
        `${name === "app_secret" ? "App secret" : "Verify token"} saved. The value is never returned.`,
      );
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not save webhook secret",
      );
    } finally {
      setWebhookSecretValues((current) => ({ ...current, [name]: "" }));
      setSavingWebhookSecret(null);
    }
  }

  // Twilio testing & sync state
  const [testBusy, setTestBusy] = useState(false);
  const [syncBusy, setSyncBusy] = useState(false);

  // Disconnect & Delete modal state
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [disconnectBusy, setDisconnectBusy] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);

  async function handleDisconnect() {
    setDisconnectBusy(true);
    try {
      await api(`/integrations/${connectionId}/disconnect`, { method: "POST" });
      toast.success(
        isTwilio
          ? "Twilio Voice integration disconnected and credentials cleared"
          : "WhatsApp integration disconnected and credentials cleared",
      );
      setDisconnectOpen(false);
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Disconnect failed");
    } finally {
      setDisconnectBusy(false);
    }
  }

  async function handleDelete() {
    setDeleteBusy(true);
    try {
      await api(`/integrations/${connectionId}`, { method: "DELETE" });
      toast.success(
        isTwilio
          ? "Twilio Voice integration deleted"
          : "Integration and associated tools deleted",
      );
      setDeleteOpen(false);
      navigate("/integrations");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Delete failed");
    } finally {
      setDeleteBusy(false);
    }
  }

  async function handleTestConnection() {
    setTestBusy(true);
    try {
      const res = await api<{
        status: "ok" | "warning";
        account_type?: string;
        phone_numbers?: Array<{ phone_number: string; friendly_name: string; voice: boolean; sid: string }>;
        message?: string;
      }>(`/integrations/${connectionId}/test`, { method: "POST" });
      if (res.status === "ok") {
        toast.success(
          `Twilio connection verified! (${res.account_type ?? "Full"} account, ${res.phone_numbers?.length ?? 0} voice numbers available)`,
        );
      } else {
        toast.warning(
          res.message || "Twilio is connected, but this account is not ready for voice calls.",
          { duration: 8000 },
        );
      }
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Connection test failed",
      );
    } finally {
      setTestBusy(false);
    }
  }

  async function handleRefreshNumbers() {
    setSyncBusy(true);
    try {
      const res = await api<{
        phone_numbers: Array<{
          phone_number: string;
          friendly_name: string;
          voice: boolean;
          sid: string;
        }>;
      }>(`/integrations/${connectionId}/refresh-numbers`, { method: "POST" });
      toast.success(`Synchronized ${res.phone_numbers.length} voice numbers from Twilio`);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Failed to refresh phone numbers",
      );
    } finally {
      setSyncBusy(false);
    }
  }

  // Templates state
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [templateBusy, setTemplateBusy] = useState(false);

  // Generate tool from template state
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(
    null,
  );
  const [toolSheetOpen, setToolSheetOpen] = useState(false);
  const [toolName, setToolName] = useState("");
  const [toolDesc, setToolDesc] = useState("");
  const [parameterDescriptions, setParameterDescriptions] = useState<
    Record<string, string>
  >({});
  const [headerMediaId, setHeaderMediaId] = useState("");
  const [toolBusy, setToolBusy] = useState(false);

  function openEditSheet() {
    if (!connection) return;
    setLabel(connection.label);
    setEnabled(connection.enabled);
    if (connection.provider === "twilio_voice") {
      setAccountSid(connection.config?.account_sid || "");
      setCredentialId(connection.credential_id || "");
    } else {
      setPhoneId(connection.config?.phone_number_id || "");
      setWabaId(connection.config?.waba_id || "");
      setApiVersion(connection.config?.api_version || "");
    }
    setEditOpen(true);
  }

  async function handleSaveAccount(event: FormEvent) {
    event.preventDefault();
    if (!connection) return;
    setEditBusy(true);
    try {
      const config =
        connection.provider === "twilio_voice"
          ? {
              ...connection.config,
              account_sid: accountSid.trim(),
            }
          : {
              ...connection.config,
              phone_number_id: phoneId.trim(),
              waba_id: wabaId.trim(),
              api_version: apiVersion.trim(),
            };

      await api<Connection>(`/integrations/${connectionId}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: label.trim(),
          enabled,
          config,
          expected_updated_at: connection.updated_at,
          credential_id: credentialId || null,
        }),
      });
      toast.success("Account settings updated successfully");
      setEditOpen(false);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not update integration settings",
      );
    } finally {
      setEditBusy(false);
    }
  }

  async function loadTemplates() {
    setTemplateBusy(true);
    try {
      const response = await api<{ templates: Template[] }>(
        `/integrations/${connectionId}/templates`,
      );
      setTemplates(response.templates);
      toast.success(`Loaded ${response.templates.length} templates from Meta`);
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not load templates from Meta",
      );
    } finally {
      setTemplateBusy(false);
    }
  }

  function handleOpenToolSheet(template: Template) {
    setSelectedTemplate(template);
    setHeaderMediaId("");
    setParameterDescriptions({});
    const sanitizedName = `whatsapp_template_${template.name
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, "_")}`;
    setToolName(sanitizedName);
    setToolDesc(
      `Send Meta WhatsApp template "${template.name}" (${template.language || "en_US"}). Automatically enforces 24h customer window or template messaging format.`,
    );
    setToolSheetOpen(true);
  }

  async function handleGenerateTool(event: FormEvent) {
    event.preventDefault();
    if (!selectedTemplate) return;
    setToolBusy(true);
    try {
      const result = await api<
        components["schemas"]["GeneratedTemplateToolResponse"]
      >(`/integrations/${connectionId}/generate-template-tool`, {
        method: "POST",
        body: JSON.stringify({
          template_name: selectedTemplate.name,
          language: selectedTemplate.language || "en_US",
          tool_name: toolName.trim() || undefined,
          description: toolDesc.trim() || undefined,
          header_media_id: headerMediaId || undefined,
          parameter_descriptions: parameterDescriptions,
          parameter_mappings: templateParameterMappings(selectedTemplate),
        }),
      });
      toast.success(
        `Tool "${result.tool_name}" (v${result.version_number}) created with parameters: ${
          result.extracted_variables.length > 0
            ? result.extracted_variables.join(", ")
            : "none (static template)"
        }`,
      );
      setToolSheetOpen(false);
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Failed to generate tool",
      );
    } finally {
      setToolBusy(false);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title={connection?.label ?? "Integration"}
        description={
          isTwilio
            ? "Twilio Voice account settings, named provider credential, and synchronized phone numbers."
            : "WhatsApp account settings, named provider credential, and media."
        }
        action={
          <Button asChild variant="outline">
            <Link to="/integrations">All integrations</Link>
          </Button>
        }
        readOnlyAction={
          <div className="flex items-center gap-2">
            <Button asChild variant="outline">
              <Link to="/integrations">All integrations</Link>
            </Button>
          </div>
        }
      />
      <LoadState
        loading={loading}
        error={error}
        empty={!connection ? "Connection not found." : undefined}
      >
        {connection && (
          <>
            <nav
              aria-label="Integration sections"
              className="flex flex-wrap gap-1 border-b pb-2"
            >
              {sections.map((item) => (
                <Button
                  type="button"
                  size="sm"
                  key={item}
                  variant={section === item ? "secondary" : "ghost"}
                  onClick={() => setParams({ section: item.toLowerCase() })}
                >
                  {item}
                </Button>
              ))}
            </nav>

            {section === "Account" && (
              <section className="flex max-w-2xl flex-col gap-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-semibold">
                      Account Configuration
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      {isTwilio
                        ? "Twilio Programmable Voice account credentials and live status."
                        : "Meta WhatsApp Business account identifiers and status."}
                    </p>
                  </div>
                  {canManage && <div className="flex items-center gap-2">
                    {isTwilio && (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={testBusy}
                          onClick={() => void handleTestConnection()}
                          className="gap-1.5"
                        >
                          <RefreshCw
                            className={`size-3.5 ${testBusy ? "animate-spin" : ""}`}
                          />
                          {testBusy ? "Testing…" : "Test connection"}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={syncBusy}
                          onClick={() => void handleRefreshNumbers()}
                          className="gap-1.5"
                        >
                          <Phone
                            className={`size-3.5 ${syncBusy ? "animate-spin" : ""}`}
                          />
                          {syncBusy ? "Syncing…" : "Sync numbers"}
                        </Button>
                      </>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5"
                      onClick={openEditSheet}
                    >
                      <Pencil className="size-3.5" />
                      Edit settings
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-amber-500 hover:text-amber-600 gap-1.5"
                      onClick={() => setDisconnectOpen(true)}
                    >
                      <PowerOff className="size-3.5" />
                      Disconnect
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="text-destructive hover:bg-destructive/10 hover:text-destructive gap-1.5"
                      onClick={() => setDeleteOpen(true)}
                    >
                      <Trash2 className="size-3.5" />
                      Delete
                    </Button>
                  </div>}
                </div>

                <div className="rounded-lg border bg-card p-4">
                  <ReadOnlyValue label="Provider" value={connection.provider} />
                  <ReadOnlyValue
                    label="Status"
                    value={
                      <div className="flex items-center gap-2">
                        {connection.deleted_at ? (
                          <Badge
                            variant="secondary"
                            className="text-muted-foreground"
                          >
                            Disconnected
                          </Badge>
                        ) : (
                          <StatusBadge
                            value={connection.enabled ? "enabled" : "disabled"}
                          />
                        )}
                        {!connection.enabled && !connection.deleted_at && (
                          <span className="text-xs text-amber-500">
                            {!connection.credential_id
                              ? `Named ${isTwilio ? "Twilio" : "WhatsApp"} credential required`
                              : linkedCredentialLoading
                                ? "Checking named credential…"
                                : selectedCredential?.status !== "stored"
                                  ? `Named credential ${selectedCredential?.status ?? (linkedCredentialUnavailable ? "unavailable" : "not found")}`
                                  : "Ready to enable"}
                          </span>
                        )}
                      </div>
                    }
                  />

                  {isTwilio ? (
                    <>
                      <ReadOnlyValue
                        label="Account SID"
                        value={
                          <code className="text-xs">
                            {connection.config.account_sid || "Not set"}
                          </code>
                        }
                      />
                      <ReadOnlyValue
                        label="Account Type"
                        value={
                          connection.config.account_type === "Trial" ? (
                            <div className="flex items-center gap-2">
                              <Badge variant="destructive">Trial</Badge>
                              <span className="text-xs text-amber-500">
                                Twilio Media Streams are blocked on Trial
                                accounts. Must upgrade to Full.
                              </span>
                            </div>
                          ) : connection.config.account_type === "Full" ? (
                            <Badge
                              variant="outline"
                              className="text-emerald-500 border-emerald-500/30"
                            >
                              Full (Production)
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              Not verified (Click "Test connection")
                            </span>
                          )
                        }
                      />
                      <ReadOnlyValue
                        label="Phone numbers"
                        value={
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-medium">
                              {connection.config.phone_numbers?.length ?? 0}{" "}
                              numbers configured
                            </span>
                            <Button
                              variant="link"
                              size="sm"
                              className="h-auto p-0 text-xs"
                              onClick={() =>
                                setParams({ section: "phone numbers" })
                              }
                            >
                              View all
                            </Button>
                          </div>
                        }
                      />
                      <ReadOnlyValue
                        label="Telephony Webhook URL"
                        value={
                          connection.webhook_url ? (
                            <code className="break-all text-xs">
                              {connection.webhook_url}
                            </code>
                          ) : (
                            <span className="text-amber-500">
                              Set VOICE_PUBLIC_BASE_URL before dispatching
                              Twilio calls.
                            </span>
                          )
                        }
                      />
                    </>
                  ) : (
                    <>
                      <ReadOnlyValue
                        label="Phone number ID"
                        value={
                          <code className="text-xs">
                            {connection.config.phone_number_id}
                          </code>
                        }
                      />
                      <ReadOnlyValue
                        label="WABA ID"
                        value={
                          <code className="text-xs">
                            {connection.config.waba_id}
                          </code>
                        }
                      />
                      <ReadOnlyValue
                        label="Meta API version"
                        value={
                          <Badge variant="outline">
                            {connection.config.api_version}
                          </Badge>
                        }
                      />
                      <ReadOnlyValue
                        label="Webhook callback URL"
                        value={
                          connection.webhook_url ? (
                            <code className="break-all text-xs">
                              {connection.webhook_url}
                            </code>
                          ) : (
                            <span className="text-amber-500">
                              Set VOICE_PUBLIC_BASE_URL before configuring Meta.
                            </span>
                          )
                        }
                      />
                    </>
                  )}

                  <ReadOnlyValue
                    label="Named provider credential"
                    value={selectedCredential ? (
                      <div className="flex items-center gap-2">
                        <span>{selectedCredential.name}</span>
                        <Badge variant={selectedCredential.status === "stored" ? "secondary" : "destructive"}>
                          {selectedCredential.status}
                        </Badge>
                      </div>
                    ) : connection.credential_id ? (
                      <span className="text-amber-500">
                        {linkedCredentialLoading ? "Loading linked credential…" : "Linked credential details unavailable"}
                      </span>
                    ) : (
                      <span className="text-amber-500">
                        None linked — select a named credential in Edit settings
                      </span>
                    )}
                  />
                </div>

                {!isTwilio && (
                  <section className="rounded-lg border bg-card p-4">
                    <div className="mb-4">
                      <h2 className="text-sm font-semibold">
                        Webhook verification
                      </h2>
                      <p className="text-xs text-muted-foreground">
                        These are separate from the named Meta API token: the
                        app secret verifies webhook signatures, and the verify
                        token is used during Meta’s webhook setup challenge.
                        Values are write-only.
                      </p>
                    </div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      {([
                        ["app_secret", "Meta app secret"],
                        ["verify_token", "Webhook verify token"],
                      ] as const).map(([name, label]) => (
                        <form
                          key={name}
                          onSubmit={(event) => {
                            event.preventDefault();
                            void saveWebhookSecret(name);
                          }}
                          className="flex flex-col gap-2"
                        >
                          <FieldLabel htmlFor={`webhook-${name}`}>
                            {label}
                          </FieldLabel>
                          <Input
                            id={`webhook-${name}`}
                            type="password"
                            autoComplete="new-password"
                            value={webhookSecretValues[name]}
                            onChange={(event) =>
                              setWebhookSecretValues((current) => ({
                                ...current,
                                [name]: event.target.value,
                              }))
                            }
                            disabled={!canManage || savingWebhookSecret !== null}
                            placeholder={
                              connection.secret_names.includes(name)
                                ? "Configured — enter a replacement"
                                : "Not configured"
                            }
                          />
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs text-muted-foreground">
                              {connection.secret_names.includes(name)
                                ? "Configured"
                                : "Missing"}
                            </span>
                            {canManage && (
                              <Button
                                type="submit"
                                size="sm"
                                variant="outline"
                                disabled={
                                  !webhookSecretValues[name] ||
                                  savingWebhookSecret !== null
                                }
                              >
                                {savingWebhookSecret === name
                                  ? "Saving…"
                                  : "Save / replace"}
                              </Button>
                            )}
                          </div>
                        </form>
                      ))}
                    </div>
                  </section>
                )}

                {/* Edit Account Sheet */}
                <Sheet open={editOpen} onOpenChange={setEditOpen}>
                  <SheetContent>
                    <form
                      onSubmit={handleSaveAccount}
                      className="flex h-full flex-col gap-6"
                    >
                      <SheetHeader>
                        <SheetTitle>Edit Account Settings</SheetTitle>
                        <SheetDescription>
                          {isTwilio
                            ? "Update Twilio Account SID and toggle call dispatch status."
                            : "Update Meta WhatsApp account identifiers and enable live dispatch."}
                        </SheetDescription>
                      </SheetHeader>

                      <FieldGroup>
                        <Field>
                          <FieldLabel htmlFor="edit-label">Label</FieldLabel>
                          <Input
                            id="edit-label"
                            value={label}
                            onChange={(e) => setLabel(e.target.value)}
                            required
                          />
                        </Field>

                        <Field>
                          <FieldLabel htmlFor="edit-enabled">Status</FieldLabel>
                          <NativeSelect
                            id="edit-enabled"
                            value={enabled ? "true" : "false"}
                            onChange={(e) =>
                              setEnabled(e.target.value === "true")
                            }
                          >
                            <NativeSelectOption value="false">
                              Disabled
                            </NativeSelectOption>
                            <NativeSelectOption value="true">
                              Enabled (Active)
                            </NativeSelectOption>
                          </NativeSelect>
                          <FieldDescription>
                            The connection can only be enabled with an active,
                            compatible named provider credential.
                          </FieldDescription>
                        </Field>

                        {isTwilio ? (
                          <>
                          <Field>
                            <FieldLabel htmlFor="edit-twilio-credential">Named Twilio credential</FieldLabel>
                            <NativeSelect id="edit-twilio-credential" value={credentialId} onChange={(event) => setCredentialId(event.target.value)}>
                              <option value="">Select a credential</option>
                              {credentialId && !compatibleCredentials.some((item) => item.id === credentialId) && <option value={credentialId}>{selectedCredential?.name ?? "Currently linked credential"}{selectedCredential ? ` · ${selectedCredential.status}` : ""}</option>}
                              {twilioCredentials.map((item) => <option key={item.id} value={item.id} disabled={item.status !== "stored"}>{item.name} · v{item.version}{item.status !== "stored" ? ` · ${item.status}` : ""}</option>)}
                            </NativeSelect>
                            <FieldDescription>Choose the saved Account SID, REST API key and webhook Auth Token bundle from Organization settings.</FieldDescription>
                          </Field>
                          <Field>
                            <FieldLabel htmlFor="edit-account-sid">
                              Account SID
                            </FieldLabel>
                            <Input
                              id="edit-account-sid"
                              value={accountSid}
                              onChange={(e) => setAccountSid(e.target.value)}
                              pattern="^AC[a-zA-Z0-9]{32}$"
                              placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                              required
                            />
                              <FieldDescription>
                              Must match the Account SID in the selected Twilio credential.
                            </FieldDescription>
                          </Field>
                          </>
                        ) : (
                          <>
                            <Field>
                              <FieldLabel htmlFor="edit-whatsapp-credential">Named WhatsApp credential</FieldLabel>
                            <NativeSelect id="edit-whatsapp-credential" value={credentialId} onChange={(event) => setCredentialId(event.target.value)}>
                              <option value="">Select a credential</option>
                                {credentialId && !compatibleCredentials.some((item) => item.id === credentialId) && <option value={credentialId}>{selectedCredential?.name ?? "Currently linked credential"}{selectedCredential ? ` · ${selectedCredential.status}` : ""}</option>}
                                {whatsappCredentials.map((item) => <option key={item.id} value={item.id} disabled={item.status !== "stored"}>{item.name} · v{item.version}{item.status !== "stored" ? ` · ${item.status}` : ""}</option>)}
                              </NativeSelect>
                              <FieldDescription>Choose the saved Meta access token from Organization settings.</FieldDescription>
                            </Field>
                            <Field>
                              <FieldLabel htmlFor="edit-phone-id">
                                Phone number ID
                              </FieldLabel>
                              <Input
                                id="edit-phone-id"
                                inputMode="numeric"
                                pattern="[0-9]+"
                                value={phoneId}
                                onChange={(e) => setPhoneId(e.target.value)}
                                required
                              />
                            </Field>

                            <Field>
                              <FieldLabel htmlFor="edit-waba-id">
                                WABA ID
                              </FieldLabel>
                              <Input
                                id="edit-waba-id"
                                inputMode="numeric"
                                pattern="[0-9]+"
                                value={wabaId}
                                onChange={(e) => setWabaId(e.target.value)}
                                required
                              />
                            </Field>

                            <Field>
                              <FieldLabel htmlFor="edit-api-version">
                                Meta API version
                              </FieldLabel>
                              <Input
                                id="edit-api-version"
                                pattern="v[0-9]+\.0"
                                placeholder="v23.0"
                                value={apiVersion}
                                onChange={(e) => setApiVersion(e.target.value)}
                                required
                              />
                              <FieldDescription>
                                Graph API version matching your Meta app (e.g.
                                v23.0).
                              </FieldDescription>
                            </Field>
                          </>
                        )}
                      </FieldGroup>

                      <SheetFooter className="mt-auto">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => setEditOpen(false)}
                        >
                          Cancel
                        </Button>
                        <Button type="submit" disabled={editBusy}>
                          {editBusy ? "Saving…" : "Save changes"}
                        </Button>
                      </SheetFooter>
                    </form>
                  </SheetContent>
                </Sheet>
              </section>
            )}

            {section === "Phone Numbers" && isTwilio && (
              <section className="flex flex-col gap-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h2 className="text-base font-semibold">
                      Twilio Phone Numbers
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      Voice-capable incoming phone numbers synchronized from
                      this Twilio account.
                    </p>
                  </div>
                  {canManage && <Button
                    variant="outline"
                    size="sm"
                    disabled={syncBusy}
                    onClick={() => void handleRefreshNumbers()}
                    className="gap-1.5"
                  >
                    <RefreshCw
                      className={`size-3.5 ${syncBusy ? "animate-spin" : ""}`}
                    />
                    {syncBusy ? "Syncing…" : "Refresh from Twilio"}
                  </Button>}
                </div>

                {!connection.config.phone_numbers ||
                connection.config.phone_numbers.length === 0 ? (
                  <Card className="border-dashed">
                    <CardHeader className="text-center">
                      <CardTitle className="text-base">
                        No Phone Numbers Synchronized
                      </CardTitle>
                      <CardDescription>
                        Link a named Twilio credential in Account settings, then
                        click "Refresh from Twilio" to fetch voice phone numbers.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                ) : (
                  <div className="rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Phone Number</TableHead>
                          <TableHead>Friendly Name</TableHead>
                          <TableHead>Voice Enabled</TableHead>
                          <TableHead className="text-right">SID</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {connection.config.phone_numbers.map((pn: any) => (
                          <TableRow key={pn.sid || pn.phone_number}>
                            <TableCell className="font-mono text-sm font-medium">
                              {pn.phone_number}
                            </TableCell>
                            <TableCell className="text-sm">
                              {pn.friendly_name || "-"}
                            </TableCell>
                            <TableCell>
                              {pn.voice ? (
                                <Badge
                                  variant="secondary"
                                  className="text-emerald-500"
                                >
                                  Voice
                                </Badge>
                              ) : (
                                <Badge variant="outline">Non-voice</Badge>
                              )}
                            </TableCell>
                            <TableCell className="text-right font-mono text-xs text-muted-foreground">
                              {pn.sid}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </section>
            )}

            {section === "Media" && !isTwilio && (
              <MediaPanel connectionId={connectionId} />
            )}

            {section === "Templates" && !isTwilio && (
              <section className="flex flex-col gap-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h2 className="text-base font-semibold">Meta Templates</h2>
                    <p className="text-xs text-muted-foreground">
                      Approved message templates from Meta WABA. Generate
                      versioned tools to send them during calls.
                    </p>
                  </div>
                  {canManage && <Button
                    variant="outline"
                    disabled={templateBusy}
                    onClick={() => void loadTemplates()}
                    className="gap-1.5"
                  >
                    <RefreshCw
                      className={`size-3.5 ${templateBusy ? "animate-spin" : ""}`}
                    />
                    {templateBusy ? "Fetching…" : "Sync from Meta"}
                  </Button>}
                </div>

                {templates === null && (
                  <Card className="border-dashed">
                    <CardHeader className="text-center">
                      <CardTitle className="text-base">
                        Templates Not Loaded
                      </CardTitle>
                      <CardDescription>
                        Click "Sync from Meta" to fetch templates configured
                        under this WhatsApp Business Account.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                )}

                {templates !== null && templates.length === 0 && (
                  <Card className="border-dashed">
                    <CardHeader className="text-center">
                      <CardTitle className="text-base">
                        No Templates Found
                      </CardTitle>
                      <CardDescription>
                        No approved templates were returned by Meta Graph API
                        for this WABA.
                      </CardDescription>
                    </CardHeader>
                  </Card>
                )}

                {templates !== null && templates.length > 0 && (
                  <div className="rounded-lg border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Template Name</TableHead>
                          <TableHead>Language</TableHead>
                          <TableHead>Category</TableHead>
                          <TableHead>Status</TableHead>
                          <TableHead className="text-right">Actions</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {templates.map((tpl) => (
                          <TableRow key={`${tpl.name}-${tpl.language}`}>
                            <TableCell className="font-mono text-sm font-medium">
                              {tpl.name}
                            </TableCell>
                            <TableCell>
                              <Badge variant="outline">
                                {tpl.language ?? "en_US"}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs text-muted-foreground">
                              {tpl.category ?? "UTILITY"}
                            </TableCell>
                            <TableCell>
                              <StatusBadge
                                value={
                                  tpl.status?.toLowerCase() ?? "unspecified"
                                }
                              />
                            </TableCell>
                            <TableCell className="text-right">
                              {canManage && <Button
                                size="sm"
                                variant="secondary"
                                className="gap-1.5"
                                onClick={() => handleOpenToolSheet(tpl)}
                              >
                                <Wrench className="size-3.5" />
                                Create Tool
                              </Button>}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}

                {/* Generate Tool Sheet */}
                <Sheet open={toolSheetOpen} onOpenChange={setToolSheetOpen}>
                  <SheetContent>
                    <form
                      onSubmit={handleGenerateTool}
                      className="flex h-full flex-col gap-6"
                    >
                      <SheetHeader>
                        <SheetTitle>Generate Template Tool</SheetTitle>
                        <SheetDescription>
                          Create an immutable, versioned tool for this Meta
                          template that agents can invoke in flow nodes.
                        </SheetDescription>
                      </SheetHeader>

                      <FieldGroup>
                        <Field>
                          <FieldLabel>Template Name</FieldLabel>
                          <Input
                            value={selectedTemplate?.name ?? ""}
                            disabled
                            className="bg-muted font-mono"
                          />
                        </Field>

                        <Field>
                          <FieldLabel>Language</FieldLabel>
                          <Input
                            value={selectedTemplate?.language ?? "en_US"}
                            disabled
                            className="bg-muted"
                          />
                        </Field>
                        <Field>
                          <FieldLabel>Header image</FieldLabel>
                          <WhatsAppMediaPicker
                            connectionId={connectionId}
                            selectedProviderId={headerMediaId || null}
                            onSelect={(mediaId) =>
                              setHeaderMediaId(mediaId ?? "")
                            }
                          />
                          <FieldDescription>
                            Required for templates with an image header. The
                            generated tool keeps the Meta media ID;
                            authenticated preview uses the catalog record.
                          </FieldDescription>
                        </Field>

                        {templateParameterNames(selectedTemplate).map(
                          (name) => (
                            <Field key={name}>
                              <FieldLabel htmlFor={`parameter-${name}`}>
                                {name} description
                              </FieldLabel>
                              <Textarea
                                id={`parameter-${name}`}
                                value={parameterDescriptions[name] ?? ""}
                                onChange={(e) =>
                                  setParameterDescriptions((current) => ({
                                    ...current,
                                    [name]: e.target.value,
                                  }))
                                }
                                rows={2}
                                required
                              />
                              <FieldDescription>
                                Helps the agent provide the correct value for
                                this template variable.
                              </FieldDescription>
                            </Field>
                          ),
                        )}
                        <Field>
                          <FieldLabel htmlFor="tool-name">Tool Name</FieldLabel>
                          <Input
                            id="tool-name"
                            value={toolName}
                            onChange={(e) => setToolName(e.target.value)}
                            pattern="^[a-zA-Z0-9_]{1,64}$"
                            required
                          />
                          <FieldDescription>
                            Identifier used in agent flow configuration. Must be
                            alphanumeric with underscores.
                          </FieldDescription>
                        </Field>

                        <Field>
                          <FieldLabel htmlFor="tool-desc">
                            Description
                          </FieldLabel>
                          <Textarea
                            id="tool-desc"
                            value={toolDesc}
                            onChange={(e) => setToolDesc(e.target.value)}
                            rows={3}
                            required
                          />
                          <FieldDescription>
                            LLM tool instruction guiding when the voice agent
                            should call this template.
                          </FieldDescription>
                        </Field>
                      </FieldGroup>

                      <SheetFooter className="mt-auto">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => setToolSheetOpen(false)}
                        >
                          Cancel
                        </Button>
                        <Button
                          type="submit"
                          disabled={toolBusy}
                          className="gap-1.5"
                        >
                          <CheckCircle2 className="size-4" />
                          {toolBusy ? "Generating…" : "Generate Tool"}
                        </Button>
                      </SheetFooter>
                    </form>
                  </SheetContent>
                </Sheet>
              </section>
            )}
          </>
        )}
      </LoadState>
      {/* Disconnect Modal */}
      <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-amber-500">
              <PowerOff className="size-5" />
              Disconnect {isTwilio ? "Twilio Voice" : "WhatsApp"} Integration
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to disconnect{" "}
              <strong>{connection?.label}</strong>?
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 text-xs text-muted-foreground space-y-2">
            <p>
              Disconnecting will immediately disable active{" "}
              {isTwilio ? "call" : "message"} dispatch and securely purge stored
              API access tokens and secrets.
            </p>
            <p>
              The connection record will be preserved with a{" "}
              <strong>Disconnected</strong> status so past call run receipts
              remain intact.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={disconnectBusy}
              onClick={() => setDisconnectOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="bg-amber-600 hover:bg-amber-700"
              disabled={disconnectBusy}
              onClick={handleDisconnect}
            >
              {disconnectBusy ? "Disconnecting…" : "Disconnect"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Modal */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="size-5" />
              Delete {isTwilio ? "Twilio Voice" : "WhatsApp"} Integration
            </DialogTitle>
            <DialogDescription>
              Are you sure you want to completely delete{" "}
              <strong>{connection?.label}</strong>?
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-4 text-xs text-destructive space-y-2">
            <p className="font-semibold uppercase tracking-wider">
              Side Effects &amp; Cascading Deletions:
            </p>
            <ul className="list-inside list-disc space-y-1">
              {isTwilio ? (
                <>
                  <li>
                    Stored credentials and telephony connection configuration
                    will be permanently destroyed.
                  </li>
                  <li>
                    Outbound calls can no longer be dispatched through this
                    Twilio connection.
                  </li>
                </>
              ) : (
                <>
                  <li>
                    All generated WhatsApp tools (e.g. template and direct
                    message tools) will be permanently deleted from the Tools
                    catalog.
                  </li>
                  <li>
                    These tools will be automatically unbound and removed from
                    all agent configurations and flow nodes.
                  </li>
                  <li>
                    Stored credentials, uploaded media, and webhook message logs
                    for this connection will be permanently destroyed.
                  </li>
                </>
              )}
            </ul>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              disabled={deleteBusy}
              onClick={() => setDeleteOpen(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={deleteBusy}
              onClick={handleDelete}
            >
              {deleteBusy ? "Deleting…" : "Delete permanently"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
}
