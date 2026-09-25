import { useState, type FormEvent } from "react";
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
              <form onSubmit={create} className="flex h-full flex-col gap-6">
                <SheetHeader>
                  <SheetTitle>New contact</SheetTitle>
                  <SheetDescription>
                    Use international phone format. Leave timezone unknown if
                    not confirmed.
                  </SheetDescription>
                </SheetHeader>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="contact-name">Name</FieldLabel>
                    <Input
                      id="contact-name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      maxLength={120}
                      required
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="contact-phone">
                      Phone number
                    </FieldLabel>
                    <Input
                      id="contact-phone"
                      type="tel"
                      value={phone}
                      onChange={(event) => setPhone(event.target.value)}
                      placeholder="+15551234567"
                      required
                      pattern="\+[1-9][0-9]{7,14}"
                    />
                    <FieldDescription>
                      Include + and country code.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="contact-timezone">Timezone</FieldLabel>
                    <Input
                      id="contact-timezone"
                      value={timezone}
                      onChange={(event) => setTimezone(event.target.value)}
                      placeholder="Asia/Kolkata"
                    />
                    <FieldDescription>
                      IANA timezone, not UTC offset.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="contact-business">Business</FieldLabel>
                    <Input
                      id="contact-business"
                      value={business}
                      onChange={(event) => setBusiness(event.target.value)}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="contact-source">Source</FieldLabel>
                    <Input
                      id="contact-source"
                      value={source}
                      onChange={(event) => setSource(event.target.value)}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="contact-language">Language</FieldLabel>
                    <Input
                      id="contact-language"
                      value={language}
                      onChange={(event) => setLanguage(event.target.value)}
                      placeholder="en-IN"
                    />
                  </Field>
                </FieldGroup>
                <SheetFooter className="mt-auto">
                  <Button type="submit" disabled={busy}>
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
                <TableCell className="font-medium">{contact.name}</TableCell>
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
        Editing, deleting and contact facts need API routes. This page offers
        list and create only.
      </p>
    </PageBody>
  );
}
