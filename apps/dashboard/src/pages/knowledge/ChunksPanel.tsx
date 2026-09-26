import { useMemo, useState } from "react";
import { Check, Copy, Database, FileText, Search } from "lucide-react";
import { toast } from "sonner";
import { LoadState } from "@/components/record-page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useResource } from "@/lib/resources";

type Chunk = {
  id: string;
  source_id: string;
  source_title: string;
  ordinal: number;
  content: string;
  char_count: number;
  metadata?: Record<string, unknown>;
};

export function ChunksPanel({ baseId }: { baseId: string }) {
  const { data, loading, error } = useResource<{ chunks: Chunk[] }>(
    `/knowledge-bases/${baseId}/chunks`
  );
  const [filterText, setFilterText] = useState("");
  const [selectedSource, setSelectedSource] = useState<string>("all");
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const sources = useMemo(() => {
    if (!data?.chunks) return [];
    const map = new Map<string, string>();
    for (const chunk of data.chunks) {
      map.set(chunk.source_id, chunk.source_title);
    }
    return Array.from(map.entries()).map(([id, title]) => ({ id, title }));
  }, [data?.chunks]);

  const filteredChunks = useMemo(() => {
    if (!data?.chunks) return [];
    return data.chunks.filter((chunk) => {
      if (selectedSource !== "all" && chunk.source_id !== selectedSource) {
        return false;
      }
      if (filterText.trim()) {
        const query = filterText.toLowerCase();
        return (
          chunk.content.toLowerCase().includes(query) ||
          chunk.source_title.toLowerCase().includes(query)
        );
      }
      return true;
    });
  }, [data?.chunks, selectedSource, filterText]);

  const copyToClipboard = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success("Chunk content copied to clipboard");
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Indexed Chunks</h2>
          <p className="text-xs text-muted-foreground">
            Inspecting {filteredChunks.length} of {data?.chunks.length ?? 0} total embedding chunks stored in pgvector.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {sources.length > 1 && (
            <NativeSelect
              value={selectedSource}
              onChange={(e) => setSelectedSource(e.target.value)}
              className="text-xs h-8"
            >
              <NativeSelectOption value="all">All Sources</NativeSelectOption>
              {sources.map((s) => (
                <NativeSelectOption key={s.id} value={s.id}>
                  {s.title}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}

          <div className="relative min-w-48">
            <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
            <Input
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Filter chunks…"
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>
      </div>

      <LoadState
        loading={loading}
        error={error}
        empty={data?.chunks.length === 0 ? "No chunks indexed yet. Add or upload sources to generate chunks." : undefined}
      >
        <div className="flex flex-col gap-3">
          {filteredChunks.map((chunk) => (
            <article
              key={chunk.id}
              className="rounded-lg border bg-card p-3.5 text-card-foreground shadow-xs transition-colors hover:border-accent-foreground/20"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 mb-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[11px] gap-1 font-mono">
                    <Database className="size-3" />
                    Chunk #{chunk.ordinal + 1}
                  </Badge>
                  <span className="flex items-center gap-1 text-xs font-medium text-foreground">
                    <FileText className="size-3 text-muted-foreground" />
                    {chunk.source_title}
                  </span>
                </div>

                <div className="flex items-center gap-3">
                  <span className="text-[11px] text-muted-foreground">
                    {chunk.char_count} chars
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => copyToClipboard(chunk.id, chunk.content)}
                  >
                    {copiedId === chunk.id ? (
                      <Check className="size-3 text-emerald-600" />
                    ) : (
                      <Copy className="size-3" />
                    )}
                    <span className="sr-only">Copy</span>
                  </Button>
                </div>
              </div>

              <div className="rounded-md bg-muted/40 p-2.5 font-mono text-xs whitespace-pre-wrap leading-relaxed">
                {chunk.content}
              </div>
            </article>
          ))}
        </div>
      </LoadState>
    </section>
  );
}
