import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { Activity, Edit3, Phone, Plus, ShieldCheck, Trash2, User } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { AdminOnly } from "@/app/access";
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
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PhoneInput } from "@/components/ui/phone-input";
import { SearchableSelect } from "@/components/ui/searchable-select";
import { getTimezones, LANGUAGES } from "@/lib/geo-data";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResource } from "@/lib/resources";

type ContactFactRecord = {
  id: string;
  name: string;
  value: unknown;
  run_id: string;
  supersedes_id: string | null;
  occurred_at: string | null;
  created_at: string | null;
};

type ContactRunRecord = {
  id: string;
  status: string;
  channel: string;
  created_at: string | null;
  started_at: string | null;
  ended_at: string | null;
  error: string | null;
};

type ContactDetailResponse = {
  id: string;
  name: string;
  phone_number: string;
  timezone: string | null;
  business: string | null;
  source: string | null;
  language: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  facts: ContactFactRecord[];
  runs: ContactRunRecord[];
};

export function ContactDetailPage() {
  const { contactId = "" } = useParams();
  const api = useApi();
  const { data, loading, error, reload } =
    useResource<ContactDetailResponse>(`/contacts/${contactId}`);

  const [editOpen, setEditOpen] = useState(false);
  const [editBusy, setEditBusy] = useState(false);

  // Edit form state
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [timezone, setTimezone] = useState("");
  const [business, setBusiness] = useState("");
  const [source, setSource] = useState("");
  const [language, setLanguage] = useState("");
  const [metadataEntries, setMetadataEntries] = useState<
    Array<{ key: string; value: string }>
  >([]);

  function addMetadataEntry() {
    setMetadataEntries((prev) => [...prev, { key: "", value: "" }]);
  }

  function updateMetadataEntry(index: number, field: "key" | "value", val: string) {
    setMetadataEntries((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: val };
      return next;
    });
  }

  function removeMetadataEntry(index: number) {
    setMetadataEntries((prev) => prev.filter((_, i) => i !== index));
  }

  useEffect(() => {
    if (data) {
      setName(data.name);
      setPhone(data.phone_number);
      setTimezone(data.timezone || "");
      setBusiness(data.business || "");
      setSource(data.source || "");
      setLanguage(data.language || "");
      const meta = data.metadata || {};
      setMetadataEntries(
        Object.entries(meta).map(([key, value]) => ({
          key,
          value: value === null || value === undefined ? "" : String(value),
        }))
      );
    }
  }, [data]);

  async function updateContact(e: FormEvent) {
    e.preventDefault();
    setEditBusy(true);

    const metadata_json: Record<string, string> = {};
    for (const entry of metadataEntries) {
      const k = entry.key.trim().toLowerCase().replace(/[^a-z0-9_.]+/g, "_");
      if (k && entry.value.trim()) {
        metadata_json[k] = entry.value.trim();
      }
    }

    try {
      await api(`/contacts/${contactId}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: name.trim(),
          phone_number: phone.trim(),
          timezone: timezone.trim() || null,
          business: business.trim() || null,
          source: source.trim() || null,
          language: language.trim() || null,
          metadata_json,
        }),
      });
      toast.success("Contact updated");
      setEditOpen(false);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Failed to update contact",
      );
    } finally {
      setEditBusy(false);
    }
  }

  function formatValue(value: unknown): string {
    if (value === null || value === undefined) return "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  return (
    <PageBody>
      <PageHeader
        title={data?.name ?? "Contact"}
        description={`Destination ${data?.phone_number ?? ""} · Times interpreted in ${data?.timezone || "unspecified timezone"}`}
        action={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => setEditOpen(true)}
              disabled={!data}
            >
              <Edit3 className="mr-1.5 size-4" />
              Edit details
            </Button>
            <Button asChild variant="outline">
              <Link to="/contacts">All contacts</Link>
            </Button>
          </div>
        }
        readOnlyAction={<Button asChild variant="outline"><Link to="/contacts">All contacts</Link></Button>}
      />

      <LoadState
        loading={loading}
        error={error}
        empty={!data ? "Contact not found." : undefined}
      >
        {data && (
          <div className="flex flex-col gap-10">
            {/* Profile Overview */}
            <section className="grid max-w-4xl gap-6 md:grid-cols-2">
              <div className="rounded-lg border bg-card p-5 text-card-foreground">
                <h3 className="mb-4 text-sm font-semibold">Contact Details</h3>
                <ReadOnlyValue label="Full name" value={data.name} />
                <ReadOnlyValue label="Phone number" value={data.phone_number} />
                <ReadOnlyValue
                  label="IANA Timezone"
                  value={data.timezone || "Not configured"}
                />
                <ReadOnlyValue
                  label="Registered business"
                  value={data.business || "—"}
                />
              </div>

              <div className="rounded-lg border bg-card p-5 text-card-foreground">
                <h3 className="mb-4 text-sm font-semibold">Context & Provenance</h3>
                <ReadOnlyValue
                  label="Acquisition source"
                  value={data.source || "—"}
                />
                <ReadOnlyValue
                  label="Preferred language"
                  value={data.language || "—"}
                />
                <ReadOnlyValue
                  label="Created timestamp"
                  value={
                    data.created_at
                      ? new Date(data.created_at).toLocaleString()
                      : "—"
                  }
                />
                <ReadOnlyValue
                  label="Contact ID"
                  value={data.id}
                  reason="Permanent database primary key."
                />
              </div>

              {/* Custom Ad & Lead Metadata Card */}
              <div className="rounded-lg border bg-card p-5 text-card-foreground md:col-span-2">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold">Custom Ad & Lead Metadata</h3>
                    <p className="text-xs text-muted-foreground">
                      Dynamic variables passed to voice agent prompts during calls.
                    </p>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {Object.keys(data.metadata || {}).length} variables
                  </Badge>
                </div>
                {Object.keys(data.metadata || {}).length === 0 ? (
                  <p className="text-xs text-muted-foreground italic">
                    No custom metadata stored for this contact. Click "Edit details" to add ad or campaign variables.
                  </p>
                ) : (
                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                    {Object.entries(data.metadata || {}).map(([key, val]) => (
                      <div key={key} className="rounded border bg-muted/30 p-2.5">
                        <div className="text-[11px] font-medium text-muted-foreground">
                          <code>{`{{ ${key} }}`}</code>
                        </div>
                        <div
                          className="mt-1 text-sm font-semibold text-foreground truncate"
                          title={String(val)}
                        >
                          {formatValue(val)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>

            {/* Verified Facts */}
            <section className="flex flex-col gap-3">
              <div>
                <h2 className="text-base font-semibold">Observed Facts</h2>
                <p className="text-xs text-muted-foreground">
                  Durable context extracted from call evidence and caller statements.
                </p>
              </div>

              {data.facts.length === 0 ? (
                <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                  No facts recorded for this contact yet. Facts are populated during call analysis.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Fact Key</TableHead>
                      <TableHead>Value</TableHead>
                      <TableHead>Recorded at</TableHead>
                      <TableHead>Source Run</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.facts.map((fact) => (
                      <TableRow key={fact.id}>
                        <TableCell className="font-medium text-foreground">
                          {fact.name}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {formatValue(fact.value)}
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {fact.occurred_at
                            ? new Date(fact.occurred_at).toLocaleString()
                            : "—"}
                        </TableCell>
                        <TableCell>
                          <Button asChild size="sm" variant="ghost">
                            <Link to={`/runs/${fact.run_id}`}>
                              Run #{fact.run_id.slice(0, 8)}
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </section>

            {/* Past Runs */}
            <section className="flex flex-col gap-3">
              <div>
                <h2 className="text-base font-semibold">Call & Run History</h2>
                <p className="text-xs text-muted-foreground">
                  All telephone calls placed to or received from this destination.
                </p>
              </div>

              {data.runs.length === 0 ? (
                <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
                  No call runs recorded for this contact yet.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Run ID</TableHead>
                      <TableHead>Channel</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Started at</TableHead>
                      <TableHead>Error</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.runs.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-mono text-xs font-semibold">
                          #{r.id.slice(0, 8)}
                        </TableCell>
                        <TableCell className="capitalize">{r.channel}</TableCell>
                        <TableCell>
                          <StatusBadge value={r.status} />
                        </TableCell>
                        <TableCell className="text-xs text-muted-foreground">
                          {r.started_at
                            ? new Date(r.started_at).toLocaleString()
                            : r.created_at
                              ? new Date(r.created_at).toLocaleString()
                              : "—"}
                        </TableCell>
                        <TableCell className="max-w-xs truncate text-xs text-destructive">
                          {r.error || "—"}
                        </TableCell>
                        <TableCell className="text-right">
                          <Button asChild size="sm" variant="outline">
                            <Link to={`/runs/${r.id}`}>Inspect</Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </section>
          </div>
        )}
      </LoadState>

      {/* Edit Contact Sheet */}
      <AdminOnly><Sheet open={editOpen} onOpenChange={setEditOpen}>
        <SheetContent>
          <form onSubmit={updateContact} className="flex min-h-full flex-col justify-between gap-4">
            <SheetHeader className="pb-1">
              <SheetTitle>Edit Contact</SheetTitle>
              <SheetDescription>
                Profile, international destination, and regional timezone settings.
              </SheetDescription>
            </SheetHeader>

            <FieldGroup className="gap-3">
              <Field className="gap-1">
                <FieldLabel htmlFor="edit-name">Full name</FieldLabel>
                <Input
                  id="edit-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Jane Doe"
                  required
                />
              </Field>

              <Field className="gap-1">
                <div className="flex items-center justify-between">
                  <FieldLabel htmlFor="edit-phone">Phone number</FieldLabel>
                  <span className="text-[11px] text-muted-foreground">Select country or type +E.164</span>
                </div>
                <PhoneInput
                  id="edit-phone"
                  value={phone}
                  onChange={setPhone}
                  required
                />
              </Field>

              <Field className="gap-1">
                <div className="flex items-center justify-between">
                  <FieldLabel htmlFor="edit-timezone">IANA Timezone</FieldLabel>
                  <span className="text-[11px] text-muted-foreground">For callback due calculations</span>
                </div>
                <SearchableSelect
                  id="edit-timezone"
                  value={timezone}
                  onChange={setTimezone}
                  options={getTimezones()}
                  placeholder="Search timezone (e.g. Asia/Kolkata, America/New_York)..."
                />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field className="gap-1">
                  <FieldLabel htmlFor="edit-business">Organization</FieldLabel>
                  <Input
                    id="edit-business"
                    value={business}
                    onChange={(e) => setBusiness(e.target.value)}
                    placeholder="e.g. Acme Corp"
                  />
                </Field>

                <Field className="gap-1">
                  <FieldLabel htmlFor="edit-source">Acquisition</FieldLabel>
                  <Input
                    id="edit-source"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    placeholder="e.g. Inbound / Web"
                  />
                </Field>
              </div>

              <Field className="gap-1">
                <FieldLabel htmlFor="edit-language">Preferred language</FieldLabel>
                <SearchableSelect
                  id="edit-language"
                  value={language}
                  onChange={setLanguage}
                  options={LANGUAGES}
                  placeholder="Search language (e.g. en-US, hi-IN)..."
                />
              </Field>

              <div className="flex flex-col gap-2 rounded-lg border p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-semibold">Custom Ad & Lead Metadata</span>
                    <p className="text-[11px] text-muted-foreground">
                      Key-values usable as prompt variables (e.g. campaign, ad_headline)
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={addMetadataEntry}
                  >
                    <Plus className="mr-1 size-3" />
                    Add field
                  </Button>
                </div>

                {metadataEntries.length === 0 ? (
                  <p className="py-1 text-[11px] text-muted-foreground italic">
                    No custom metadata. Click "Add field" to store ad or lead tags.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2 pt-1">
                    {metadataEntries.map((entry, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <Input
                          placeholder="Key (e.g. campaign)"
                          value={entry.key}
                          onChange={(e) =>
                            updateMetadataEntry(idx, "key", e.target.value)
                          }
                          className="h-8 text-xs font-mono"
                        />
                        <Input
                          placeholder="Value (e.g. spring_sale)"
                          value={entry.value}
                          onChange={(e) =>
                            updateMetadataEntry(idx, "value", e.target.value)
                          }
                          className="h-8 text-xs"
                        />
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="size-8 text-muted-foreground hover:text-destructive"
                          onClick={() => removeMetadataEntry(idx)}
                          aria-label="Remove metadata entry"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </FieldGroup>

            <SheetFooter className="border-t pt-3 mt-auto">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setEditOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={editBusy}>
                {editBusy ? "Saving…" : "Save Changes"}
              </Button>
            </SheetFooter>
          </form>
        </SheetContent>
      </Sheet></AdminOnly>
    </PageBody>
  );
}
