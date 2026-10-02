import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "@clerk/react";
import { toast } from "sonner";
import { KeyRound, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useOrganizationAccess } from "@/app/access";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useResource } from "@/lib/resources";
import { SettingsNavigation } from "./SettingsNavigation";

type Credential = components["schemas"]["CredentialStatus"];
type Provider = Credential["provider"];
type SecretFields = {
  name: string;
  api_key: string;
  account_sid: string;
  api_key_sid: string;
  api_key_secret: string;
  auth_token: string;
};

const emptyFields: SecretFields = {
  name: "",
  api_key: "",
  account_sid: "",
  api_key_sid: "",
  api_key_secret: "",
  auth_token: "",
};

const providers: Array<{ id: Provider; label: string; purpose: string }> = [
  {
    id: "gnani",
    label: "Gnani",
    purpose: "Prisma speech recognition and Timbre speech synthesis",
  },
  {
    id: "isoquant",
    label: "Isoquant",
    purpose: "GLM-5.3-Flash for voice, classification and summaries",
  },
  {
    id: "sarvam",
    label: "Sarvam",
    purpose: "Voice models, speech recognition, and synthesis",
  },
  {
    id: "groq",
    label: "Groq",
    purpose: "Voice agent, classifier, and summarizer",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    purpose: "Account specific language models",
  },
  {
    id: "gemini",
    label: "Google Gemini",
    purpose: "Voice agent, classification, and knowledge search",
  },
  { id: "cartesia", label: "Cartesia", purpose: "Speech synthesis" },
  { id: "jev", label: "JEV", purpose: "Lead classification" },
  {
    id: "whatsapp",
    label: "WhatsApp Cloud",
    purpose: "Meta WhatsApp Cloud API access",
  },
  {
    id: "twilio",
    label: "Twilio",
    purpose: "Voice account, REST access, and webhook verification",
  },
];

export function CredentialsSettingsPage() {
  const api = useApi();
  const { orgId } = useAuth();
  const { canManage } = useOrganizationAccess();
  const { data, loading, error, reload } = useResource<Credential[]>(
    orgId ? `/orgs/${orgId}/credentials` : "",
    Boolean(orgId),
  );
  const [selectedProvider, setSelectedProvider] = useState<Provider>("groq");
  const [formProvider, setFormProvider] = useState<Provider>("groq");
  const [formOpen, setFormOpen] = useState(false);
  const [fields, setFields] = useState<SecretFields>(emptyFields);
  const [replacement, setReplacement] = useState<Credential | null>(null);
  const [saving, setSaving] = useState(false);
  const [renameTarget, setRenameTarget] = useState<Credential | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Credential | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    setFields(emptyFields);
    setReplacement(null);
    setFormOpen(false);
  }, [orgId]);

  const credentials = data ?? [];
  const visibleCredentials = credentials.filter(
    (item) => item.provider === selectedProvider,
  );
  const currentProvider = providers.find(
    (item) => item.id === selectedProvider,
  )!;
  const providerCounts = new Map(
    providers.map((item) => [
      item.id,
      credentials.filter(
        (credential) =>
          credential.provider === item.id && credential.status !== "deleted",
      ).length,
    ]),
  );

  function clearForm() {
    setFields(emptyFields);
    setReplacement(null);
  }

  function begin(providerId: Provider, credential?: Credential) {
    setSelectedProvider(providerId);
    setFormProvider(providerId);
    setReplacement(credential ?? null);
    setFields({ ...emptyFields, name: credential?.name ?? "" });
    setFormOpen(true);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!orgId || !fields.name.trim()) return;
    let saved = false;
    setSaving(true);
    try {
      const body =
        formProvider === "twilio"
          ? {
              ...fields,
              provider: formProvider,
              ...(replacement ? { expected_version: replacement.version } : {}),
            }
          : {
              name: fields.name,
              provider: formProvider,
              api_key: fields.api_key,
              ...(replacement ? { expected_version: replacement.version } : {}),
            };
      await api(
        replacement
          ? `/orgs/${orgId}/credentials/${replacement.id}`
          : `/orgs/${orgId}/credentials`,
        {
          method: replacement ? "PUT" : "POST",
          body: JSON.stringify(body),
        },
      );
      toast.success(
        replacement
          ? "Credential replaced for future calls"
          : "Credential added securely",
      );
      saved = true;
      setFormOpen(false);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not save credential",
      );
    } finally {
      setFields((current) => ({
        ...emptyFields,
        name: saved ? "" : current.name,
      }));
      if (saved) setReplacement(null);
      setSaving(false);
    }
  }

  async function rename() {
    if (!orgId || !renameTarget || !renameValue.trim()) return;
    setRenameBusy(true);
    try {
      await api(`/orgs/${orgId}/credentials/${renameTarget.id}/name`, {
        method: "PATCH",
        body: JSON.stringify({
          name: renameValue.trim(),
          expected_version: renameTarget.version,
        }),
      });
      toast.success("Credential renamed");
      setRenameTarget(null);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not rename credential",
      );
    } finally {
      setRenameBusy(false);
    }
  }

  async function remove() {
    if (!orgId || !deleteTarget) return;
    setDeleteBusy(true);
    try {
      await api(`/orgs/${orgId}/credentials/${deleteTarget.id}`, {
        method: "DELETE",
        body: JSON.stringify({ expected_version: deleteTarget.version }),
      });
      toast.success("Credential removed from this application");
      setDeleteTarget(null);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not delete credential",
      );
    } finally {
      setDeleteBusy(false);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title="Provider credentials"
        description="Manage encrypted provider keys for this organization. Secret values are write only."
        action={
          canManage ? (
            <Button onClick={() => begin(selectedProvider)}>
              <Plus className="size-4" />
              Add credential
            </Button>
          ) : undefined
        }
      />
      <SettingsNavigation active="/settings/credentials" />
      <div className="grid min-w-0 gap-6 md:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="min-w-0 md:border-r md:pr-4">
          <p className="mb-2 px-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Providers
          </p>
          <nav
            aria-label="Credential providers"
            className="flex gap-1 overflow-x-auto md:flex-col md:overflow-visible"
          >
            {providers.map((item) => {
              const selected = item.id === selectedProvider;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-current={selected ? "true" : undefined}
                  onClick={() => setSelectedProvider(item.id)}
                  className={`flex shrink-0 items-center justify-between gap-4 rounded-md px-3 py-2.5 text-left text-sm transition-colors md:w-full ${selected ? "bg-primary/10 font-medium text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"}`}
                >
                  <span>{item.label}</span>
                  <Badge
                    variant={selected ? "default" : "secondary"}
                    className="tabular-nums"
                  >
                    {providerCounts.get(item.id) ?? 0}
                  </Badge>
                </button>
              );
            })}
          </nav>
        </aside>

        <section className="min-w-0">
          <header className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b pb-4">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <KeyRound className="size-4 text-primary" />
                <h2 className="font-semibold">{currentProvider.label}</h2>
                <Badge variant="secondary">
                  {visibleCredentials.length}{" "}
                  {visibleCredentials.length === 1 ? "key" : "keys"}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {currentProvider.purpose}
              </p>
            </div>
          </header>

          <LoadState loading={loading} error={error}>
            {visibleCredentials.length === 0 ? (
              <div className="flex flex-col items-start gap-3 py-8">
                <p className="font-medium">
                  No {currentProvider.label} credentials
                </p>
                <p className="max-w-lg text-sm text-muted-foreground">
                  Add a named credential to let configured integrations or
                  agents use {currentProvider.label}.
                </p>
                {canManage && (
                  <Button onClick={() => begin(selectedProvider)}>
                    <Plus className="size-4" />
                    Add {currentProvider.label} credential
                  </Button>
                )}
              </div>
            ) : (
              <div className="divide-y border-y">
                {visibleCredentials.map((item) => {
                  const isDeleted = item.status === "deleted";
                  return (
                    <article
                      key={item.id}
                      className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="font-medium">{item.name}</h3>
                          <StatusBadge value={item.status} />
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Version {item.version}{" "}
                          <span aria-hidden="true">·</span>{" "}
                          <span title={item.id}>ID {item.id.slice(0, 8)}</span>
                        </p>
                      </div>
                      {canManage && !isDeleted && (
                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => begin(item.provider, item)}
                          >
                            <RefreshCw className="size-3.5" />
                            Replace
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setRenameTarget(item);
                              setRenameValue(item.name);
                            }}
                          >
                            <Pencil className="size-3.5" />
                            Rename
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-destructive hover:text-destructive"
                            onClick={() => setDeleteTarget(item)}
                          >
                            <Trash2 className="size-3.5" />
                            Delete
                          </Button>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </LoadState>

          <p className="mt-5 max-w-2xl text-xs leading-relaxed text-muted-foreground">
            Keys are encrypted by the API and never returned to this page or
            saved in browser storage. Removing a credential here does not revoke
            the key with its provider.
          </p>
        </section>
      </div>

      <Sheet
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open && !saving) clearForm();
        }}
      >
        <SheetContent>
          <form
            onSubmit={(event) => void save(event)}
            className="flex h-full flex-col gap-6 overflow-y-auto"
          >
            <SheetHeader>
              <SheetTitle>
                {replacement
                  ? `Replace ${replacement.name}`
                  : `Add ${providers.find((item) => item.id === formProvider)?.label} credential`}
              </SheetTitle>
              <SheetDescription>
                {replacement
                  ? "Save a new version for future calls. The existing secret cannot be viewed."
                  : "Add an encrypted organization credential. Its secret will only be submitted once."}
              </SheetDescription>
            </SheetHeader>
            <FieldGroup>
              {!replacement && (
                <Field>
                  <FieldLabel htmlFor="credential-provider">
                    Provider
                  </FieldLabel>
                  <NativeSelect
                    id="credential-provider"
                    value={formProvider}
                    onChange={(event) => {
                      setFormProvider(event.target.value as Provider);
                      setFields(emptyFields);
                    }}
                  >
                    {providers.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </NativeSelect>
                </Field>
              )}
              <Field>
                <FieldLabel htmlFor="credential-name">
                  Credential name
                </FieldLabel>
                <Input
                  id="credential-name"
                  maxLength={120}
                  value={fields.name}
                  onChange={(event) =>
                    setFields({ ...fields, name: event.target.value })
                  }
                  required
                />
              </Field>
              {formProvider === "twilio" ? (
                <>
                  <SecretInput
                    id="twilio-account-sid"
                    label="Twilio Account SID"
                    value={fields.account_sid}
                    onChange={(value) =>
                      setFields({ ...fields, account_sid: value })
                    }
                  />
                  <SecretInput
                    id="twilio-api-sid"
                    label="Twilio API Key SID"
                    value={fields.api_key_sid}
                    onChange={(value) =>
                      setFields({ ...fields, api_key_sid: value })
                    }
                  />
                  <SecretInput
                    id="twilio-api-secret"
                    label="Twilio API Key Secret (REST)"
                    value={fields.api_key_secret}
                    onChange={(value) =>
                      setFields({ ...fields, api_key_secret: value })
                    }
                  />
                  <SecretInput
                    id="twilio-auth-token"
                    label="Twilio Auth Token (webhook signature)"
                    value={fields.auth_token}
                    onChange={(value) =>
                      setFields({ ...fields, auth_token: value })
                    }
                  />
                </>
              ) : (
                <SecretInput
                  id="provider-api-key"
                  label={
                    formProvider === "whatsapp"
                      ? "WhatsApp Cloud access token"
                      : "API key"
                  }
                  value={fields.api_key}
                  onChange={(value) => setFields({ ...fields, api_key: value })}
                />
              )}
              <FieldDescription>
                Secret fields clear after saving and are never displayed again.
              </FieldDescription>
            </FieldGroup>
            <SheetFooter>
              <Button type="submit" disabled={saving || !fields.name.trim()}>
                {saving
                  ? "Saving…"
                  : replacement
                    ? "Replace for future calls"
                    : "Save credential"}
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet>

      <Dialog
        open={Boolean(renameTarget)}
        onOpenChange={(open) => {
          if (!open && !renameBusy) setRenameTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rename credential</DialogTitle>
            <DialogDescription>
              Renaming changes the label only. The stored secret is unchanged.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor="rename-credential">Credential name</FieldLabel>
            <Input
              id="rename-credential"
              maxLength={120}
              value={renameValue}
              onChange={(event) => setRenameValue(event.target.value)}
              autoFocus
            />
          </Field>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRenameTarget(null)}
              disabled={renameBusy}
            >
              Cancel
            </Button>
            <Button
              onClick={() => void rename()}
              disabled={renameBusy || !renameValue.trim()}
            >
              {renameBusy ? "Saving…" : "Save name"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this credential?</AlertDialogTitle>
            <AlertDialogDescription>
              New calls that rely on {deleteTarget?.name} will fail. This
              removes it from the application but does not revoke the key with
              its provider.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBusy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deleteBusy}
              onClick={(event) => {
                event.preventDefault();
                void remove();
              }}
            >
              {deleteBusy ? "Removing…" : "Remove credential"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageBody>
  );
}

function SecretInput({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        type="password"
        autoComplete="new-password"
        maxLength={4096}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
      />
    </Field>
  );
}
