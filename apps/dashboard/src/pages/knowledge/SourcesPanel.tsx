import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { LoadState, StatusBadge } from "@/components/record-page";
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
import { Textarea } from "@/components/ui/textarea";
import { useResource } from "@/lib/resources";
import type { KnowledgeSource } from "./types";

export function SourcesPanel({ baseId }: { baseId: string }) {
  const api = useApi();
  const { data, loading, error, reload } = useResource<{
    sources: KnowledgeSource[];
  }>(`/knowledge-bases/${baseId}/sources`);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  async function addText(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`/knowledge-bases/${baseId}/sources`, {
        method: "POST",
        body: JSON.stringify({ title: title.trim(), content, kind: "paste" }),
      });
      toast.success("Source queued for ingestion");
      setOpen(false);
      setTitle("");
      setContent("");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not add source",
      );
    } finally {
      setBusy(false);
    }
  }
  async function upload(file: File) {
    const body = new FormData();
    body.set("file", file);
    setBusy(true);
    try {
      await api(`/knowledge-bases/${baseId}/uploads`, { method: "POST", body });
      toast.success("File queued for ingestion");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not upload file",
      );
    } finally {
      setBusy(false);
    }
  }
  async function rebuild(source: KnowledgeSource) {
    try {
      await api(`/knowledge-bases/${baseId}/sources/${source.id}/rebuild`, {
        method: "POST",
      });
      toast.success("Rebuild queued");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not rebuild source",
      );
    }
  }
  async function remove(source: KnowledgeSource) {
    if (!window.confirm(`Delete ${source.title} and its chunks?`)) return;
    try {
      await api(`/knowledge-bases/${baseId}/sources/${source.id}`, {
        method: "DELETE",
      });
      toast.success("Source deleted");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not delete source",
      );
    }
  }
  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Sources</h2>
          <p className="text-xs text-muted-foreground">
            Deleting a source removes current chunks. Rebuild keeps working
            search until replacement succeeds.
          </p>
        </div>
        <div className="flex gap-2">
          <label className="inline-flex cursor-pointer items-center rounded-md border px-3 py-2 text-sm hover:bg-accent">
            Upload PDF/TXT/Markdown
            <Input
              className="sr-only"
              type="file"
              accept=".pdf,.txt,.md,text/plain,text/markdown,application/pdf"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
                event.target.value = "";
              }}
            />
          </label>
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button>Add text</Button>
            </SheetTrigger>
            <SheetContent>
              <form onSubmit={addText} className="flex h-full flex-col gap-6">
                <SheetHeader>
                  <SheetTitle>Add text source</SheetTitle>
                  <SheetDescription>
                    Paste text to ingest into current knowledge base.
                  </SheetDescription>
                </SheetHeader>
                <FieldGroup>
                  <Field>
                    <FieldLabel htmlFor="source-title">Title</FieldLabel>
                    <Input
                      id="source-title"
                      value={title}
                      onChange={(event) => setTitle(event.target.value)}
                      maxLength={240}
                      required
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="source-text">Content</FieldLabel>
                    <Textarea
                      id="source-text"
                      value={content}
                      onChange={(event) => setContent(event.target.value)}
                      required
                      className="min-h-48"
                    />
                  </Field>
                </FieldGroup>
                <SheetFooter className="mt-auto">
                  <Button
                    type="submit"
                    disabled={busy || !title.trim() || !content.trim()}
                  >
                    {busy ? "Adding…" : "Add source"}
                  </Button>
                </SheetFooter>
              </form>
            </SheetContent>
          </Sheet>
        </div>
      </div>
      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.sources.length === 0
            ? "No sources. Upload a file or paste text."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.sources.map((source) => (
              <TableRow key={source.id}>
                <TableCell>
                  <span className="font-medium">{source.title}</span>
                  {source.error && (
                    <p className="text-xs text-destructive">{source.error}</p>
                  )}
                </TableCell>
                <TableCell>{source.kind}</TableCell>
                <TableCell>
                  <StatusBadge value={source.status} />
                </TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void rebuild(source)}
                  >
                    Rebuild
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void remove(source)}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
    </section>
  );
}
