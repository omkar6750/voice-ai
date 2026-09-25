import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

type Hit = {
  chunk_id: string;
  title: string;
  content: string;
  score: number;
  score_type: string;
};

export function SearchPanel({ baseId }: { baseId: string }) {
  const api = useApi();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [busy, setBusy] = useState(false);
  async function search(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const result = await api<{ hits: Hit[] }>(
        `/knowledge-bases/${baseId}/search`,
        { method: "POST", body: JSON.stringify({ query }) },
      );
      setHits(result.hits);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="flex max-w-3xl flex-col gap-5">
      <h2 className="text-base font-semibold">Search test</h2>
      <form className="flex items-end gap-2" onSubmit={search}>
        <Field>
          <FieldLabel htmlFor="kb-query">Query</FieldLabel>
          <Input
            id="kb-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
          />
          <FieldDescription>
            Uses backend retrieval defaults. Agent-specific retrieval settings
            are on agent version.
          </FieldDescription>
        </Field>
        <Button type="submit" disabled={busy || !query.trim()}>
          {busy ? "Searching…" : "Search"}
        </Button>
      </form>
      {hits?.length === 0 && (
        <p className="text-sm text-muted-foreground">No matching chunks.</p>
      )}
      {hits?.map((hit, index) => (
        <article key={hit.chunk_id} className="border-b py-3">
          <div className="flex items-center justify-between gap-2 text-sm">
            <strong>
              {index + 1}. {hit.title}
            </strong>
            <span className="text-xs text-muted-foreground">
              {hit.score_type}: {hit.score.toFixed(3)}
            </span>
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm">{hit.content}</p>
        </article>
      ))}
    </section>
  );
}
