import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import type { components } from "@/generated/api";
import { useResource } from "@/lib/resources";
import {
  LoadState,
  PageBody,
  PageHeader,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
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

type Referral = components["schemas"]["ReferralResponse"];
type Page = components["schemas"]["ReferralPage"];
type Review = components["schemas"]["ReferralReview"];

function ReferralEditor({
  referral,
  onSaved,
}: {
  referral: Referral;
  onSaved: () => void;
}) {
  const api = useApi();
  const { canManage } = useOrganizationAccess();
  const [draft, setDraft] = useState(referral);
  const [savedReview, setSavedReview] = useState(referral);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked = !canManage || draft.status === "converted" || busy;
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const body: Review = {
      first_name: draft.first_name,
      last_name: draft.last_name,
      phone_number: draft.phone_number,
      email: draft.email,
      organization: draft.organization,
      role: draft.role,
      context: draft.context,
      contact_details_confirmed: draft.contact_details_confirmed,
      phone_verification_status: draft.phone_verification_status,
      email_verification_status: draft.email_verification_status,
      status: draft.status === "converted" ? "reviewed" : draft.status,
      expected_updated_at: draft.updated_at,
    };
    try {
      const saved = await api<Referral>(`/referrals/${draft.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setDraft(saved);
      setSavedReview(saved);
      onSaved();
      toast.success("Referral updated");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save referral",
      );
    } finally {
      setBusy(false);
    }
  }
  async function promote() {
    setBusy(true);
    setError(null);
    try {
      const result = await api<
        components["schemas"]["ReferralPromotionResponse"]
      >(`/referrals/${draft.id}/promote`, { method: "POST" });
      setDraft({
        ...draft,
        status: "converted",
        promoted_contact_id: result.contact_id,
      });
      onSaved();
      toast.success(
        result.existing_contact
          ? "Linked to existing contact"
          : "Contact created",
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not create contact",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save} className="flex flex-col gap-5 p-4">
      <div className="rounded-lg border bg-muted/40 p-3 text-sm">
        <p>
          Caller confirmed readback:{" "}
          {draft.contact_details_confirmed
            ? "Yes"
            : "No contact details confirmed"}
        </p>
        <p className="mt-1 text-muted-foreground">
          Readback confirms what was said. Phone and email ownership remain
          unverified until reviewed separately.
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          {draft.referrer_contact_id && (
            <Link
              className="text-primary underline"
              to={`/contacts/${draft.referrer_contact_id}`}
            >
              Original caller
            </Link>
          )}
          {draft.source_run_id && (
            <Link
              className="text-primary underline"
              to={`/runs/${draft.source_run_id}`}
            >
              Source conversation
            </Link>
          )}
          {draft.promoted_contact_id && (
            <Link
              className="text-primary underline"
              to={`/contacts/${draft.promoted_contact_id}`}
            >
              Created contact
            </Link>
          )}
        </div>
      </div>
      <fieldset disabled={locked}>
        <FieldGroup>
          {(
            [
              ["first_name", "First name"],
              ["last_name", "Last name"],
              ["phone_number", "Phone number"],
              ["email", "Email"],
              ["organization", "Organization"],
              ["role", "Role"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key}>
              <FieldLabel htmlFor={`referral-${key}`}>{label}</FieldLabel>
              <Input
                id={`referral-${key}`}
                value={draft[key] ?? ""}
                required={key === "first_name"}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    [key]: event.target.value || null,
                    ...(key === "phone_number"
                      ? { phone_verification_status: "unverified" as const }
                      : {}),
                    ...(key === "email"
                      ? { email_verification_status: "unverified" as const }
                      : {}),
                  })
                }
              />
            </Field>
          ))}
          <Field>
            <FieldLabel htmlFor="referral-context">Referral context</FieldLabel>
            <Textarea
              id="referral-context"
              value={draft.context ?? ""}
              onChange={(event) =>
                setDraft({ ...draft, context: event.target.value || null })
              }
            />
          </Field>
          {(
            [
              ["phone_verification_status", "Phone ownership"],
              ["email_verification_status", "Email ownership"],
            ] as const
          ).map(([key, label]) => (
            <Field key={key}>
              <FieldLabel htmlFor={`referral-${key}`}>{label}</FieldLabel>
              <NativeSelect
                id={`referral-${key}`}
                value={draft[key]}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    [key]: event.target.value as "verified" | "unverified",
                  })
                }
              >
                <NativeSelectOption value="unverified">
                  Unverified
                </NativeSelectOption>
                <NativeSelectOption value="verified">
                  Verified by operator
                </NativeSelectOption>
              </NativeSelect>
            </Field>
          ))}
          <Field>
            <FieldLabel htmlFor="referral-status">Review status</FieldLabel>
            <NativeSelect
              id="referral-status"
              value={draft.status}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  status: event.target.value as Referral["status"],
                })
              }
            >
              <NativeSelectOption value="pending_review">
                Pending review
              </NativeSelectOption>
              <NativeSelectOption value="reviewed">Reviewed</NativeSelectOption>
              <NativeSelectOption value="dismissed">
                Dismissed
              </NativeSelectOption>
              {draft.status === "converted" && (
                <NativeSelectOption value="converted">
                  Converted
                </NativeSelectOption>
              )}
            </NativeSelect>
            <FieldDescription>
              Saving a referral never sends a message or schedules a call.
            </FieldDescription>
          </Field>
        </FieldGroup>
      </fieldset>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {canManage && draft.status !== "converted" && (
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Save review"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={
              busy ||
              JSON.stringify(draft) !== JSON.stringify(savedReview) ||
              draft.phone_verification_status !== "verified" ||
              draft.status === "dismissed"
            }
            onClick={promote}
          >
            Create contact from saved review
          </Button>
          <p className="w-full text-xs text-muted-foreground">
            Save your review first. Creating a contact requires a verified
            international phone number; email-only referrals remain here.
          </p>
        </div>
      )}
    </form>
  );
}

export function ReferralsPage() {
  const api = useApi();
  const [params] = useSearchParams();
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState("");
  const [selected, setSelected] = useState<Referral | null>(null);
  const [installing, setInstalling] = useState(false);
  const query = new URLSearchParams({ limit: "50" });
  if (status) query.set("status", status);
  if (cursor) query.set("cursor", cursor);
  if (params.get("contact"))
    query.set("referrer_contact_id", params.get("contact")!);
  if (params.get("run")) query.set("source_run_id", params.get("run")!);
  const { data, loading, error, reload } = useResource<Page>(
    `/referrals?${query}`,
  );
  async function install() {
    setInstalling(true);
    try {
      await api("/referrals/tool", { method: "POST" });
      toast.success(
        "save_referral is available in Tools. Bind it to your agent's selected nodes or shared tools.",
      );
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not install tool",
      );
    } finally {
      setInstalling(false);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title="Referrals"
        description="People suggested during conversations. Review their details before creating a contact."
        action={
          <Button variant="outline" disabled={installing} onClick={install}>
            {installing ? "Installing…" : "Make referral tool available"}
          </Button>
        }
      />
      <Field className="max-w-xs">
        <FieldLabel htmlFor="referral-filter">Review status</FieldLabel>
        <NativeSelect
          id="referral-filter"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setCursor("");
          }}
        >
          <NativeSelectOption value="">All referrals</NativeSelectOption>
          {["pending_review", "reviewed", "dismissed", "converted"].map(
            (value) => (
              <NativeSelectOption key={value} value={value}>
                {value.replaceAll("_", " ")}
              </NativeSelectOption>
            ),
          )}
        </NativeSelect>
      </Field>
      <LoadState
        loading={loading}
        error={error}
        empty={
          data && !data.referrals.length
            ? "Referrals saved by the agent will appear here, including incomplete and email-only referrals."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Person</TableHead>
              <TableHead>Contact details</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Saved</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.referrals.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <Button
                    variant="link"
                    className="h-auto p-0"
                    onClick={() => setSelected(row)}
                  >
                    {row.first_name} {row.last_name}
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    {[row.role, row.organization].filter(Boolean).join(" · ")}
                  </p>
                </TableCell>
                <TableCell>
                  <p>{row.phone_number ?? "No phone supplied"}</p>
                  <p className="text-muted-foreground">
                    {row.email ?? "No email supplied"}
                  </p>
                </TableCell>
                <TableCell>
                  <StatusBadge value={row.status} />
                </TableCell>
                <TableCell>
                  {new Date(row.created_at).toLocaleString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={!cursor}
          onClick={() => setCursor("")}
        >
          First page
        </Button>
        <Button
          variant="outline"
          disabled={!data?.next_cursor}
          onClick={() => setCursor(data!.next_cursor!)}
        >
          Next page
        </Button>
      </div>
      <Sheet
        open={Boolean(selected)}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
      >
        <SheetContent className="overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Review referral</SheetTitle>
            <SheetDescription>
              Keep caller confirmation separate from verification.
            </SheetDescription>
          </SheetHeader>
          {selected && (
            <ReferralEditor
              key={selected.id}
              referral={selected}
              onSaved={() => void reload()}
            />
          )}
        </SheetContent>
      </Sheet>
    </PageBody>
  );
}
