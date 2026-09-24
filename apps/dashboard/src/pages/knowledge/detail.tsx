import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Layers,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  Sparkles,
  Trash2,
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
import { Textarea } from "@/components/ui/textarea";
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
import { NativeSelect } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";

interface SourceItem {
  id: string;
  title: string;
  kind: string;
  status: "building" | "ready" | "failed";
  error: string | null;
}

interface SearchResult {
  chunk_id: string;
  source_id: string;
  title: string;
  source_path?: string;
  content: string;
  score: number;
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
  const [busySourceId, setBusySourceId] = useState<string | null>(null);

  // Add source state
  const [openAddSheet, setOpenAddSheet] = useState(false);
  const [addingSource, setAddingSource] = useState(false);
  const [sourceTitle, setSourceTitle] = useState("");
  const [sourceKind, setSourceKind] = useState<"paste" | "md" | "txt">("paste");
  const [sourceContent, setSourceContent] = useState("");

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

  async function executeTestSearch(e: FormEvent) {
    e.preventDefault();
    if (!kbId || !testQuery.trim()) return;
    setSearching(true);
    try {
      const data = await api<{ hits: SearchResult[] }>(`/knowledge-bases/${kbId}/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: testQuery.trim(),
          retrieval: {
            top_k: 4,
          },
        }),
      });
      setSearchResults(data.hits);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Search query failed");
    } finally {
      setSearching(false);
    }
  }

  async function handleAddSource(e: FormEvent) {
    e.preventDefault();
    if (!kbId || !sourceTitle.trim() || !sourceContent.trim()) {
      toast.error("Please enter a title and document content");
      return;
    }
    setAddingSource(true);
    try {
      await api(`/knowledge-bases/${kbId}/sources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: sourceTitle.trim(),
          kind: sourceKind,
          content: sourceContent.trim(),
        }),
      });
      toast.success("Document source queued for vector embedding build");
      setOpenAddSheet(false);
      setSourceTitle("");
      setSourceContent("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to add document source");
    } finally {
      setAddingSource(false);
    }
  }

  async function handleDeleteSource(sourceId: string, title: string) {
    if (!kbId || !confirm(`Delete source '${title}' and its vector embeddings?`)) return;
    setBusySourceId(sourceId);
    try {
      await api(`/knowledge-bases/${kbId}/sources/${sourceId}`, { method: "DELETE" });
      toast.success(`Deleted source ${title}`);
      setSources((prev) => prev.filter((s) => s.id !== sourceId));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete source");
    } finally {
      setBusySourceId(null);
    }
  }

  async function handleRebuildSource(sourceId: string) {
    if (!kbId) return;
    setBusySourceId(sourceId);
    try {
      await api(`/knowledge-bases/${kbId}/sources/${sourceId}/rebuild`, { method: "POST" });
      toast.success("Embedding rebuild triggered");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to trigger rebuild");
    } finally {
      setBusySourceId(null);
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
            <Sheet open={openAddSheet} onOpenChange={setOpenAddSheet}>
              <SheetTrigger asChild>
                <Button size="sm" className="gap-1.5 bg-primary text-primary-foreground">
                  <Plus className="size-3.5" /> Add Document Source
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="flex flex-col p-6 w-full sm:max-w-lg">
                <SheetHeader className="p-0 mb-4">
                  <SheetTitle className="flex items-center gap-2 text-lg">
                    <FileText className="size-5 text-primary" />
                    Add Knowledge Source
                  </SheetTitle>
                  <SheetDescription>
                    Ingest raw text or markdown to chunk and index into pgvector embeddings.
                  </SheetDescription>
                </SheetHeader>

                <form onSubmit={handleAddSource} className="flex flex-col gap-4 flex-1 justify-between">
                  <div className="flex flex-col gap-3.5 overflow-y-auto pr-1">
                    <Field>
                      <FieldLabel htmlFor="src-title">Document Title</FieldLabel>
                      <Input
                        id="src-title"
                        placeholder="Pricing & Amenities Guide"
                        required
                        value={sourceTitle}
                        onChange={(e) => setSourceTitle(e.target.value)}
                      />
                    </Field>

                    <Field>
                      <FieldLabel htmlFor="src-kind">Source Format</FieldLabel>
                      <NativeSelect
                        id="src-kind"
                        value={sourceKind}
                        onChange={(e) => setSourceKind(e.target.value as any)}
                      >
                        <option value="paste">Plaintext / Paste</option>
                        <option value="md">Markdown (.md)</option>
                        <option value="txt">Text (.txt)</option>
                      </NativeSelect>
                    </Field>

                    <Field>
                      <FieldLabel htmlFor="src-content">Content</FieldLabel>
                      <Textarea
                        id="src-content"
                        rows={10}
                        placeholder="# Project Brief&#10;&#10;Key details about project pricing, floor plans, and amenities..."
                        required
                        className="font-mono text-xs"
                        value={sourceContent}
                        onChange={(e) => setSourceContent(e.target.value)}
                      />
                    </Field>
                  </div>

                  <div className="flex items-center justify-end gap-3 pt-4 border-t">
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setOpenAddSheet(false)}
                      disabled={addingSource}
                    >
                      Cancel
                    </Button>
                    <Button type="submit" disabled={addingSource || !sourceTitle.trim() || !sourceContent.trim()}>
                      {addingSource ? <Spinner className="size-4 mr-1.5" /> : null}
                      Ingest & Index
                    </Button>
                  </div>
                </form>
              </SheetContent>
            </Sheet>
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
                <div className="p-4 flex flex-col gap-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-full" />
                </div>
              ) : sources.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">
                  No documents in this knowledge base yet.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Document Title</TableHead>
                      <TableHead className="text-xs">Type</TableHead>
                      <TableHead className="text-xs">Status</TableHead>
                      <TableHead className="text-xs text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sources.map((src) => (
                      <TableRow key={src.id}>
                        <TableCell className="font-medium text-xs">
                          <div className="flex items-center gap-2">
                            <FileText className="size-3.5 text-muted-foreground" />
                            <span>{src.title}</span>
                          </div>
                        </TableCell>
                        <TableCell className="font-mono text-[11px] uppercase text-muted-foreground">
                          {src.kind}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={
                              src.status === "ready"
                                ? "bg-emerald-50 text-emerald-700 text-[10px] border-emerald-200"
                                : src.status === "building"
                                ? "bg-amber-50 text-amber-700 text-[10px] border-amber-200"
                                : "bg-destructive/10 text-destructive text-[10px]"
                            }
                          >
                            {src.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              title="Rebuild Embeddings"
                              disabled={busySourceId === src.id}
                              onClick={() => void handleRebuildSource(src.id)}
                            >
                              <RotateCw className="size-3 text-muted-foreground hover:text-foreground" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon-xs"
                              title="Delete Source"
                              className="text-muted-foreground hover:text-destructive"
                              disabled={busySourceId === src.id}
                              onClick={() => void handleDeleteSource(src.id, src.title)}
                            >
                              <Trash2 className="size-3" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Live Vector Similarity Tester */}
        <div className="flex flex-col gap-3">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
                <Sparkles className="size-4 text-primary" />
                Semantic Search Tester
              </CardTitle>
              <CardDescription className="text-xs">
                Test embedding similarity queries to verify what context the LLM retrieves during a call.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <form onSubmit={executeTestSearch} className="flex gap-2">
                <Input
                  placeholder="e.g. what is the pricing of 2bhk units?"
                  className="text-xs h-8"
                  value={testQuery}
                  onChange={(e) => setTestQuery(e.target.value)}
                />
                <Button type="submit" size="sm" className="h-8 text-xs" disabled={searching || !testQuery.trim()}>
                  {searching ? <Spinner className="size-3 mr-1" /> : <Search className="size-3 mr-1" />}
                  Search
                </Button>
              </form>

              {searchResults !== null && (
                <div className="flex flex-col gap-2.5">
                  <span className="text-[11px] font-medium text-muted-foreground">
                    Matches ({searchResults.length}):
                  </span>
                  {searchResults.length === 0 ? (
                    <div className="rounded-md border p-4 text-center text-xs text-muted-foreground">
                      No matching semantic chunks found for this query.
                    </div>
                  ) : (
                    searchResults.map((hit) => (
                      <div key={hit.chunk_id} className="flex flex-col gap-1 rounded-md border p-3 bg-muted/20">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold">{hit.title}</span>
                          <Badge variant="outline" className="font-mono text-[10px]">
                            score: {hit.score.toFixed(3)}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground line-clamp-4 font-sans whitespace-pre-line">
                          {hit.content}
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
