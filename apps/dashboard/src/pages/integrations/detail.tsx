import { useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  CheckCircle2,
  ExternalLink,
  Pencil,
  RefreshCw,
  Wrench,
} from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
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
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
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
import { SecretsPanel } from "./SecretsPanel";
import type { Connection } from "./index";

type Template = {
  name: string;
  status?: string;
  language?: string;
  category?: string;
};

const sections = ["Account", "Credentials", "Media", "Templates"] as const;

export function IntegrationDetailPage() {
  const { connectionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const api = useApi();
  const {
    data: connection,
    loading,
    error,
    reload,
  } = useResource<Connection>(`/integrations/${connectionId}`);

  const section =
    sections.find((item) => item.toLowerCase() === params.get("section")) ??
    "Account";

  // Account editing state
  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);
  const [label, setLabel] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [phoneId, setPhoneId] = useState("");
  const [wabaId, setWabaId] = useState("");
  const [apiVersion, setApiVersion] = useState("");

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
  const [toolBusy, setToolBusy] = useState(false);

  function openEditSheet() {
    if (!connection) return;
    setLabel(connection.label);
    setEnabled(connection.enabled);
    setPhoneId(connection.config.phone_number_id);
    setWabaId(connection.config.waba_id);
    setApiVersion(connection.config.api_version);
    setEditOpen(true);
  }

  async function handleSaveAccount(event: FormEvent) {
    event.preventDefault();
    if (!connection) return;
    setEditBusy(true);
    try {
      await api<Connection>(`/integrations/${connectionId}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: label.trim(),
          enabled,
          config: {
            phone_number_id: phoneId.trim(),
            waba_id: wabaId.trim(),
            api_version: apiVersion.trim(),
          },
          expected_updated_at: connection.updated_at,
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
      const result = await api<{
        status: string;
        tool_id: string;
        tool_name: string;
        version_number: number;
        extracted_variables: string[];
      }>(`/integrations/${connectionId}/generate-template-tool`, {
        method: "POST",
        body: JSON.stringify({
          template_name: selectedTemplate.name,
          language: selectedTemplate.language || "en_US",
          tool_name: toolName.trim() || undefined,
          description: toolDesc.trim() || undefined,
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
        description="WhatsApp account settings, credentials, and media. Secrets stay write-only on the server."
        action={
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
                      Meta WhatsApp Business account identifiers and status.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    onClick={openEditSheet}
                  >
                    <Pencil className="size-3.5" />
                    Edit settings
                  </Button>
                </div>

                <div className="rounded-lg border bg-card p-4">
                  <ReadOnlyValue label="Provider" value={connection.provider} />
                  <ReadOnlyValue
                    label="Status"
                    value={
                      <div className="flex items-center gap-2">
                        <StatusBadge
                          value={connection.enabled ? "enabled" : "disabled"}
                        />
                        {!connection.enabled &&
                          !connection.secret_names.includes(
                            "system_user_token",
                          ) && (
                            <span className="text-xs text-amber-500">
                              (Requires system_user_token credential)
                            </span>
                          )}
                      </div>
                    }
                  />
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
                    label="Configured secrets"
                    value={
                      connection.secret_names.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {connection.secret_names.map((name) => (
                            <Badge
                              key={name}
                              variant="secondary"
                              className="text-xs"
                            >
                              {name}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-amber-500">
                          None configured (Add credentials)
                        </span>
                      )
                    }
                  />
                </div>

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
                          Update Meta WhatsApp account identifiers and enable
                          live dispatch.
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
                            Must have `system_user_token` saved in Credentials
                            to enable.
                          </FieldDescription>
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
                          <FieldLabel htmlFor="edit-waba-id">WABA ID</FieldLabel>
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

            {section === "Credentials" && (
              <SecretsPanel
                connectionId={connectionId}
                configured={connection.secret_names}
                reload={reload}
              />
            )}

            {section === "Media" && <MediaPanel connectionId={connectionId} />}

            {section === "Templates" && (
              <section className="flex flex-col gap-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h2 className="text-base font-semibold">Meta Templates</h2>
                    <p className="text-xs text-muted-foreground">
                      Approved message templates from Meta WABA. Generate
                      versioned tools to send them during calls.
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    disabled={templateBusy}
                    onClick={() => void loadTemplates()}
                    className="gap-1.5"
                  >
                    <RefreshCw
                      className={`size-3.5 ${templateBusy ? "animate-spin" : ""}`}
                    />
                    {templateBusy ? "Fetching…" : "Sync from Meta"}
                  </Button>
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
                              <Button
                                size="sm"
                                variant="secondary"
                                className="gap-1.5"
                                onClick={() => handleOpenToolSheet(tpl)}
                              >
                                <Wrench className="size-3.5" />
                                Create Tool
                              </Button>
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
    </PageBody>
  );
}
