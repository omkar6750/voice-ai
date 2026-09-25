import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
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

type Base = {
  id: string;
  name: string;
  config: { embedding_model: string; embedding_dimensions: number };
};

export function KnowledgePage() {
  const api = useApi();
  const navigate = useNavigate();
  const { data, loading, error, reload } = useResource<{
    knowledge_bases: Base[];
  }>("/knowledge-bases");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api<{ id: string }>("/knowledge-bases", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      });
      toast.success("Knowledge base created");
      setOpen(false);
      setName("");
      await reload();
      navigate(`/knowledge/${result.id}`);
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not create knowledge base",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title="Knowledge"
        description="Mutable text, PDF and Markdown sources. Ingestion settings belong to each base."
        action={
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button>New knowledge base</Button>
            </SheetTrigger>
            <SheetContent>
              <form onSubmit={create} className="flex h-full flex-col gap-6">
                <SheetHeader>
                  <SheetTitle>New knowledge base</SheetTitle>
                  <SheetDescription>
                    Backend defaults apply to chunking and embeddings.
                  </SheetDescription>
                </SheetHeader>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="kb-name">Name</FieldLabel>
                    <Input
                      id="kb-name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      required
                      maxLength={120}
                    />
                  </Field>
                </FieldGroup>
                <SheetFooter className="mt-auto">
                  <Button type="submit" disabled={busy || !name.trim()}>
                    {busy ? "Creating…" : "Create"}
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
          data?.knowledge_bases.length === 0
            ? "No knowledge bases yet."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Embedding</TableHead>
              <TableHead className="text-right">Open</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.knowledge_bases.map((base) => (
              <TableRow key={base.id}>
                <TableCell className="font-medium">{base.name}</TableCell>
                <TableCell className="text-muted-foreground">
                  {base.config.embedding_model} ·{" "}
                  {base.config.embedding_dimensions}d
                </TableCell>
                <TableCell className="text-right">
                  <Button asChild variant="link">
                    <Link to={`/knowledge/${base.id}`}>Sources</Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
    </PageBody>
  );
}
