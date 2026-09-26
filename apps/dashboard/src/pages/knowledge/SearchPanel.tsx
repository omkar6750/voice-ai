import { useState, type FormEvent } from "react";
import { CheckCircle2, FileText, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Badge } from "@/components/ui/badge";
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
    if (!query.trim()) return;
    setBusy(true);
    try {
      const result = await api<{ hits: Hit[] }>(
        `/knowledge-bases/${baseId}/search`,
        {
          method: "POST",
          body: JSON.stringify({
            query: query.trim(),
            retrieval: { top_k: 5 },
          }),
        },
      );
      // Ensure only up to 5 top candidates are displayed
      setHits(result.hits.slice(0, 5));
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  const maxScore = hits && hits.length > 0 ? Math.max(...hits.map((h) => h.score), 0.0001) : 1;

  return (
    <section className="flex max-w-3xl flex-col gap-6">
      <div>
        <h2 className="text-base font-semibold">Live RAG Search Tester</h2>
        <p className="text-xs text-muted-foreground">
          Simulate hybrid semantic and keyword retrieval against this knowledge base with top-5 candidate rankings and match percentages.
        </p>
      </div>

      <form className="flex flex-col gap-3 rounded-lg border bg-muted/20 p-4" onSubmit={search}>
        <Field>
          <FieldLabel htmlFor="kb-query">Search Query</FieldLabel>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                id="kb-query"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="e.g. What is the turnaround time and pricing for MVP development?"
                className="pl-9 text-sm"
                required
              />
            </div>
            <Button type="submit" disabled={busy || !query.trim()} className="gap-2">
              <Sparkles className="size-4" />
              {busy ? "Searching…" : "Run Search"}
            </Button>
          </div>
          <FieldDescription>
            Uses hybrid vector embedding (Gemini 768-dim) and keyword reciprocal rank fusion.
          </FieldDescription>
        </Field>
      </form>

      {hits && (
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>
              Found <strong>{hits.length}</strong> top {hits.length === 1 ? "candidate" : "candidates"} (max 5)
            </span>
            {hits.length > 0 && <span>Ranked by {hits[0].score_type}</span>}
          </div>

          {hits.length === 0 ? (
            <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
              No matching chunks found for &ldquo;{query}&rdquo;.
            </div>
          ) : (
            hits.map((hit, index) => {
              // Calculate intuitive match percentage:
              // For cosine similarity (0 to 1), use direct score * 100%.
              // For RRF (scores ~0.005-0.02), compute relative rank percentage against the #1 hit.
              const percentage =
                hit.score_type === "cosine_similarity"
                  ? Math.round(Math.max(0, Math.min(1, hit.score)) * 100)
                  : Math.round((hit.score / maxScore) * 100);

              const isTop = index === 0;

              return (
                <article
                  key={hit.chunk_id}
                  className={`rounded-lg border p-4 text-card-foreground shadow-xs transition-colors ${
                    isTop ? "border-emerald-500/40 bg-emerald-500/5 dark:bg-emerald-950/10" : "bg-card"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2.5">
                    <div className="flex items-center gap-2">
                      <span className="flex size-6 items-center justify-center rounded-full bg-muted text-xs font-bold text-foreground">
                        {index + 1}
                      </span>
                      <strong className="flex items-center gap-1.5 text-sm">
                        <FileText className="size-3.5 text-muted-foreground" />
                        {hit.title}
                      </strong>
                    </div>

                    <div className="flex items-center gap-2">
                      <Badge
                        variant="outline"
                        className={`text-xs gap-1 font-semibold ${
                          percentage >= 80
                            ? "text-emerald-600 bg-emerald-500/10 border-emerald-300 dark:border-emerald-800"
                            : percentage >= 50
                              ? "text-amber-600 bg-amber-500/10 border-amber-300 dark:border-amber-800"
                              : "text-muted-foreground"
                        }`}
                      >
                        <CheckCircle2 className="size-3" />
                        {percentage}% Match
                      </Badge>
                      <span className="text-[11px] text-muted-foreground font-mono">
                        raw: {hit.score.toFixed(4)}
                      </span>
                    </div>
                  </div>

                  <p className="mt-3 whitespace-pre-wrap rounded-md bg-muted/30 p-3 text-xs leading-relaxed font-sans text-foreground">
                    {hit.content}
                  </p>
                </article>
              );
            })
          )}
        </div>
      )}
    </section>
  );
}
