import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Globe, Phone, Plus, RefreshCw, Search, Trash2, User, Users } from "lucide-react";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { NativeSelect } from "@/components/ui/native-select";

interface ContactItem {
  id: string;
  name: string;
  phone_number: string;
  timezone: string;
  business: string | null;
  source: string | null;
  language: string;
}

export function ContactsPage() {
  const api = useApi();
  const [contacts, setContacts] = useState<ContactItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // New contact sheet state
  const [openAddSheet, setOpenAddSheet] = useState(false);
  const [addingContact, setAddingContact] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newBusiness, setNewBusiness] = useState("");
  const [newLanguage, setNewLanguage] = useState("en");
  const [newTimezone, setNewTimezone] = useState("Asia/Kolkata");
  const [newSource, setNewSource] = useState("manual");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await api<{ contacts: ContactItem[] }>("/contacts");
      setContacts(data.contacts);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load contacts";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleDelete(contactId: string, name: string) {
    if (!confirm(`Are you sure you want to delete contact '${name}'?`)) return;
    setDeletingId(contactId);
    try {
      await api(`/contacts/${contactId}`, { method: "DELETE" });
      toast.success(`Deleted contact ${name}`);
      setContacts((prev) => prev.filter((c) => c.id !== contactId));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete contact");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleCreateContact(e: FormEvent) {
    e.preventDefault();
    if (!newName.trim() || !newPhone.trim()) {
      toast.error("Please enter a name and valid phone number");
      return;
    }
    setAddingContact(true);
    try {
      await api("/contacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          phone_number: newPhone.trim(),
          timezone: newTimezone,
          business: newBusiness.trim() || undefined,
          source: newSource.trim() || undefined,
          language: newLanguage,
        }),
      });
      toast.success(`Contact ${newName} created`);
      setOpenAddSheet(false);
      setNewName("");
      setNewPhone("");
      setNewBusiness("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create contact");
    } finally {
      setAddingContact(false);
    }
  }

  const filtered = contacts.filter((c) => {
    const q = query.toLowerCase();
    return (
      c.name.toLowerCase().includes(q) ||
      c.phone_number.toLowerCase().includes(q) ||
      (c.business && c.business.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Contacts & Leads</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Verified recipient phone numbers, lead context, and language preferences.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
          <Sheet open={openAddSheet} onOpenChange={setOpenAddSheet}>
            <SheetTrigger asChild>
              <Button size="sm" className="gap-1.5 bg-primary text-primary-foreground">
                <Plus className="size-3.5" /> Add Contact
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="flex flex-col p-6 w-full sm:max-w-md">
              <SheetHeader className="p-0 mb-4">
                <SheetTitle className="flex items-center gap-2 text-lg">
                  <User className="size-5 text-primary" />
                  Add New Contact
                </SheetTitle>
                <SheetDescription>
                  Register a new verified customer or lead with international E.164 phone formatting.
                </SheetDescription>
              </SheetHeader>

              <form onSubmit={handleCreateContact} className="flex flex-col gap-4 flex-1 justify-between">
                <div className="flex flex-col gap-4">
                  <Field>
                    <FieldLabel htmlFor="c-name">Full Name</FieldLabel>
                    <Input
                      id="c-name"
                      placeholder="Jane Doe"
                      required
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="c-phone">Phone Number (E.164 with country code)</FieldLabel>
                    <Input
                      id="c-phone"
                      placeholder="+919876543210"
                      required
                      value={newPhone}
                      onChange={(e) => setNewPhone(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="c-biz">Company / Business (Optional)</FieldLabel>
                    <Input
                      id="c-biz"
                      placeholder="Acme Real Estate"
                      value={newBusiness}
                      onChange={(e) => setNewBusiness(e.target.value)}
                    />
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="c-lang">Preferred Language</FieldLabel>
                    <NativeSelect
                      id="c-lang"
                      value={newLanguage}
                      onChange={(e) => setNewLanguage(e.target.value)}
                    >
                      <option value="en">English (en)</option>
                      <option value="mr">Marathi (mr)</option>
                      <option value="hi">Hindi (hi)</option>
                    </NativeSelect>
                  </Field>

                  <Field>
                    <FieldLabel htmlFor="c-tz">Timezone</FieldLabel>
                    <NativeSelect
                      id="c-tz"
                      value={newTimezone}
                      onChange={(e) => setNewTimezone(e.target.value)}
                    >
                      <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                      <option value="America/New_York">America/New_York (EST)</option>
                      <option value="Europe/London">Europe/London (GMT)</option>
                    </NativeSelect>
                  </Field>
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setOpenAddSheet(false)}
                    disabled={addingContact}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={addingContact || !newName.trim() || !newPhone.trim()}>
                    {addingContact ? <Spinner className="size-4 mr-1.5" /> : null}
                    Save Contact
                  </Button>
                </div>
              </form>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Search by name, phone, or company…"
            className="pl-8 text-xs h-8"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <Card className="p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-32 w-full" />
        </Card>
      ) : error ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Could not load contacts</EmptyTitle>
            <EmptyDescription>{error}</EmptyDescription>
          </EmptyHeader>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </Empty>
      ) : filtered.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>{query ? "No matching contacts" : "No contacts in directory"}</EmptyTitle>
            <EmptyDescription>
              {query ? "Try a different search term." : "Add contacts or import them to begin placing calls."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Card className="shadow-none">
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Contact Name</TableHead>
                  <TableHead className="text-xs">Phone Number</TableHead>
                  <TableHead className="text-xs">Business / Domain</TableHead>
                  <TableHead className="text-xs">Language & Timezone</TableHead>
                  <TableHead className="text-xs">Source</TableHead>
                  <TableHead className="text-xs text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium text-xs">
                      <div className="flex items-center gap-2">
                        <div className="flex size-6 items-center justify-center rounded-full bg-muted text-muted-foreground font-mono text-[10px]">
                          {c.name.slice(0, 1).toUpperCase()}
                        </div>
                        <span>{c.name}</span>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs text-foreground/90">
                      {c.phone_number}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {c.business || "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      <div className="flex items-center gap-1.5 font-mono text-[11px]">
                        <Badge variant="outline" className="text-[10px] px-1 py-0 font-normal">
                          {c.language}
                        </Badge>
                        <span>{c.timezone}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {c.source || "inbound"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        className="text-muted-foreground hover:text-destructive"
                        disabled={deletingId === c.id}
                        onClick={() => void handleDelete(c.id, c.name)}
                      >
                        {deletingId === c.id ? <Spinner className="size-3" /> : <Trash2 className="size-3.5" />}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
