import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";

import { LoadState, PageBody, PageHeader } from "@/components/record-page";
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
import { useResource } from "@/lib/resources";

type Contact = {
  id: string;
  name: string;
  phone_number: string;
  timezone: string | null;
  business: string | null;
  source: string | null;
  language: string | null;
};

export function ContactsPage() {
  const api = useApi();
  const { data, loading, error, reload } = useResource<{ contacts: Contact[] }>(
    "/contacts",
  );
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [timezone, setTimezone] = useState("");
  const [business, setBusiness] = useState("");
  const [source, setSource] = useState("");
  const [language, setLanguage] = useState("");

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("/contacts", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          phone_number: phone.trim(),
          timezone: timezone.trim() || null,
          business: business.trim() || null,
          source: source.trim() || null,
          language: language.trim() || null,
        }),
      });
      toast.success("Contact created");
      setOpen(false);
      setName("");
      setPhone("");
      setTimezone("");
      setBusiness("");
      setSource("");
      setLanguage("");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not create contact",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageBody>
      <PageHeader
        title="Contacts"
        description="Phone destinations and caller context. Times are interpreted in each contact's timezone."
        action={
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button>New contact</Button>
            </SheetTrigger>
            <SheetContent>
              <form onSubmit={create} className="flex min-h-full flex-col justify-between gap-4">
                <SheetHeader className="pb-1">
                  <SheetTitle>New contact</SheetTitle>
                  <SheetDescription>
                    Phone destination and context. Timezone determines callback schedule.
                  </SheetDescription>
                </SheetHeader>

                <FieldGroup className="gap-3">
                  <Field className="gap-1">
                    <FieldLabel htmlFor="contact-name">Name</FieldLabel>
                    <Input
                      id="contact-name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      maxLength={120}
                      placeholder="e.g. Omkar Pawar"
                      required
                    />
                  </Field>

                  <Field className="gap-1">
                    <div className="flex items-center justify-between">
                      <FieldLabel htmlFor="contact-phone">Phone number</FieldLabel>
                      <span className="text-[11px] text-muted-foreground">Select country or type +E.164</span>
                    </div>
                    <PhoneInput
                      id="contact-phone"
                      value={phone}
                      onChange={setPhone}
                      required
                    />
                  </Field>

                  <Field className="gap-1">
                    <div className="flex items-center justify-between">
                      <FieldLabel htmlFor="contact-timezone">IANA Timezone</FieldLabel>
                      <span className="text-[11px] text-muted-foreground">For callback due calculations</span>
                    </div>
                    <SearchableSelect
                      id="contact-timezone"
                      value={timezone}
                      onChange={setTimezone}
                      options={getTimezones()}
                      placeholder="Search timezone (e.g. Asia/Kolkata)..."
                    />
                  </Field>

                  <div className="grid grid-cols-2 gap-3">
                    <Field className="gap-1">
                      <FieldLabel htmlFor="contact-business">Organization</FieldLabel>
                      <Input
                        id="contact-business"
                        value={business}
                        onChange={(event) => setBusiness(event.target.value)}
                        placeholder="e.g. Acme Corp"
                      />
                    </Field>

                    <Field className="gap-1">
                      <FieldLabel htmlFor="contact-source">Acquisition</FieldLabel>
                      <Input
                        id="contact-source"
                        value={source}
                        onChange={(event) => setSource(event.target.value)}
                        placeholder="e.g. Inbound / Web"
                      />
                    </Field>
                  </div>

                  <Field className="gap-1">
                    <FieldLabel htmlFor="contact-language">Language</FieldLabel>
                    <SearchableSelect
                      id="contact-language"
                      value={language}
                      onChange={setLanguage}
                      options={LANGUAGES}
                      placeholder="Search language (e.g. en-US, hi-IN)..."
                    />
                  </Field>
                </FieldGroup>

                <SheetFooter className="border-t pt-3 mt-auto">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={busy}>
                    {busy ? "Creating…" : "Create contact"}
                  </Button>
                </SheetFooter>
              </form>
            </SheetContent>
          </Sheet>
        }
      />
      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.contacts.length === 0
            ? "No contacts. Add one before placing a call."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Timezone</TableHead>
              <TableHead>Business</TableHead>
              <TableHead>Language</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.contacts.map((contact) => (
              <TableRow key={contact.id}>
                <TableCell className="font-medium">
                  <Link
                    to={`/contacts/${contact.id}`}
                    className="hover:underline text-primary"
                  >
                    {contact.name}
                  </Link>
                </TableCell>
                <TableCell>{contact.phone_number}</TableCell>
                <TableCell className="text-muted-foreground">
                  {contact.timezone || "Unknown"}
                </TableCell>
                <TableCell>{contact.business || "—"}</TableCell>
                <TableCell>{contact.language || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
      <p className="text-xs text-muted-foreground">
        Click any contact name to view observed facts, call history, and edit details.
      </p>
    </PageBody>
  );
}
