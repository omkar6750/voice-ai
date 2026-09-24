import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Globe, Phone, Plus, RefreshCw, Search, User, Users } from "lucide-react";
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
