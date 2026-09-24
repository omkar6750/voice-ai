import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Layers,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
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

interface SourceItem {
  id: string;
  title: string;
  kind: string;
  status: "building" | "ready" | "failed";
  error: string | null;
  created_at: string;
}

interface SearchResult {
  chunk_id: string;
  source_id: string;
  title: string;
  content: string;
  similarity: number;
}

export function KnowledgeDetailPage() {
  const { kbId } = useParams();
  const api = useApi();
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [kbName, setKbName] = useState("Knowledge Base");
  const [loading, setLoading] = useState(true);
  const [testQuery, setTestQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);

  async function load() {
    if (!kbId) return;
    setLoading(true);
    try {
      const [kbData, sourcesData] = await Promise.all([
        api<{ knowledge_bases: Array<{ id: string; name: string }> }>("/knowledge-bases"),
        api<{ sources: SourceItem[] }>(`/knowledge-bases/${kbId}/sources`),
      ]);
      const current = kbData.knowledge_bases.find((b) => b.id === kbId);
      if (current) setKbName(current.name);
      setSources(sourcesData.sources);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load knowledge base");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [kbId]);

  async function executeTestSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!kbId || !testQuery.trim()) return;
    setSearching(true);
    try {
      const data = await api<{ matches: SearchResult[] }>(`/knowledge-bases/${kbId}/search`, {
        method: "POST",
        body: JSON.stringify({
          query: testQuery.trim(),
          limit: 3,
          min_similarity: 0.2,
        }),
      });
      setSearchResults(data.matches);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search query failed");
    } finally {
      setSearching(false);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div>
        <Link
          to="/knowledge"
          className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="size-3.5" /> Back to knowledge bases
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3 mt-1">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{kbName}</h1>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">
              KB ID: {kbId}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void load()}>
              <RefreshCw className="size-3.5 mr-1.5" /> Refresh
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Left: Document Sources */}
        <div className="flex flex-col gap-3">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Document Sources ({sources.length})</CardTitle>
              <CardDescription className="text-xs">
                Ingested Markdown, PDF, and text documentation files indexed into pgvector chunks.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {loading ? (
                <div className="p-4">
                  <Skeleton className="h-5 w-40 mb-2" />
                  <Skeleton className="h-16 w-full" />
                </div>
              ) : sources.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  No document sources ingested yet.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Document Title</TableHead>
                      <TableHead className="text-xs">Type</TableHead>
                      <TableHead className="text-xs text-right">Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.map((s) => (
                      <TableRow key={s.id}>
                        <TableCell className="font-medium text-xs">
                          <div className="flex items-center gap-2">
                            <FileText className="size-3.5 text-muted-foreground" />
                            <span>{s.title}</span>
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-xs uppercase text-muted-foreground">
                          {s.kind}
                        </TableCell>
                        <TableCell className="text-right">
                          <Badge
                            variant="outline"
                            className={
                              s.status === "ready"
                                ? "bg-emerald-50 text-emerald-700 text-[10px] border-emerald-200"
                                : s.status === "building"
                                  ? "bg-blue-50 text-blue-700 text-[10px] border-blue-200"
                                  : "bg-red-50 text-red-700 text-[10px] border-red-200"
                            }
                          >
                            {s.status}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Interactive RAG Vector Search Tester */}
        <div className="flex flex-col gap-3">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-1.5">
                <Sparkles className="size-4 text-primary" />
                <CardTitle className="text-sm font-semibold">Semantic Search Tester</CardTitle>
              </div>
              <CardDescription className="text-xs">
                Test embedding similarity queries to verify what context the LLM retrieves during a call.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <form onSubmit={executeTestSearch} className="flex gap-2">
                <Input
                  placeholder="e.g. What is the pricing for MVP sprint?"
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                  className="text-xs h-8"
                />
                <Button type="submit" size="sm" className="text-xs h-8" disabled={searching}>
                  <Search className="size-3.5 mr-1" />
                  {searching ? "Searching…" : "Search"}
                </Button>
              </form>

              {searchResults !== null && (
                <div className="flex flex-col gap-2 mt-2">
                  <span className="text-[11px] font-medium text-muted-foreground">
                    Matches ({searchResults.length}):
                  </span>
                  {searchResults.length === 0 ? (
                    <p className="text-xs text-muted-foreground italic">No chunks met the similarity threshold.</p>
                  ) : (
                    searchResults.map((m) => (
                      <div key={m.chunk_id} className="rounded-md border p-2.5 bg-muted/40 text-xs flex flex-col gap-1">
                        <div className="flex items-center justify-between text-[11px] font-mono">
                          <span className="font-semibold text-foreground">{m.title}</span>
                          <span className="text-emerald-700 bg-emerald-50 px-1 py-0.5 rounded border border-emerald-200">
                            {(m.similarity * 100).toFixed(1)}% match
                          </span>
                        </div>
                        <p className="text-muted-foreground text-[11px] whitespace-pre-wrap font-sans mt-0.5">
                          {m.content}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
