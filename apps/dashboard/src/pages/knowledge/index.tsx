import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { BookOpen, ChevronRight, Database, Plus, RefreshCw } from "lucide-react";
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Field, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";

interface KBItem {
  id: string;
  name: string;
  config: {
    chunk_size: number;
    chunk_overlap: number;
    markdown_aware: boolean;
    supported_sources: string[];
  };
}

export function KnowledgePage() {
  const api = useApi();
  const navigate = useNavigate();
  const [bases, setBases] = useState<KBItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Create knowledge base sheet state
  const [openAddSheet, setOpenAddSheet] = useState(false);
  const [creating, setCreating] = useState(false);
  const [kbName, setKbName] = useState("");
  const [chunkSize, setChunkSize] = useState(400);
  const [chunkOverlap, setChunkOverlap] = useState(50);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const data = await api<{ knowledge_bases: KBItem[] }>("/knowledge-bases");
      setBases(data.knowledge_bases);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load knowledge bases";
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreateKB(e: FormEvent) {
    e.preventDefault();
    if (!kbName.trim()) {
      toast.error("Please enter a name for the knowledge base");
      return;
    }
    setCreating(true);
    try {
      const res = await api<{ id: string; name: string }>("/knowledge-bases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: kbName.trim(),
          config: {
            chunk_size: Number(chunkSize) || 400,
            chunk_overlap: Number(chunkOverlap) || 50,
            markdown_aware: true,
            supported_sources: ["text", "markdown", "pdf"],
          },
        }),
      });
      toast.success(`Knowledge base '${kbName}' created`);
      setOpenAddSheet(false);
      setKbName("");
      navigate(`/knowledge/${res.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create knowledge base");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex flex-col gap-5 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Knowledge Bases</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Document ingestion, vector embeddings (pgvector), and semantic RAG context sources for voice agents.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
          <Sheet open={openAddSheet} onOpenChange={setOpenAddSheet}>
            <SheetTrigger asChild>
              <Button size="sm" className="gap-1.5 bg-primary text-primary-foreground">
                <Plus className="size-3.5" /> Create Knowledge Base
              </Button>
            </SheetTrigger>
            <SheetContent side="right" className="flex flex-col p-6 w-full sm:max-w-md">
              <SheetHeader className="p-0 mb-4">
                <SheetTitle className="flex items-center gap-2 text-lg">
                  <Database className="size-5 text-primary" />
                  New Knowledge Base
                </SheetTitle>
                <SheetDescription>
                  Create an isolated pgvector collection for indexing project documents and guidelines.
                </SheetDescription>
              </SheetHeader>

              <form onSubmit={handleCreateKB} className="flex flex-col gap-4 flex-1 justify-between">
                <div className="flex flex-col gap-4">
                  <Field>
                    <FieldLabel htmlFor="kb-name">Collection Name</FieldLabel>
                    <Input
                      id="kb-name"
                      placeholder="e.g. Sales FAQ & Pricing"
                      required
                      value={kbName}
                      onChange={(e) => setKbName(e.target.value)}
                    />
                  </Field>

                  <div className="grid grid-cols-2 gap-3">
                    <Field>
                      <FieldLabel htmlFor="kb-chunk">Chunk Size (chars)</FieldLabel>
                      <Input
                        id="kb-chunk"
                        type="number"
                        min={100}
                        max={4000}
                        value={chunkSize}
                        onChange={(e) => setChunkSize(Number(e.target.value))}
                      />
                    </Field>

                    <Field>
                      <FieldLabel htmlFor="kb-overlap">Overlap (chars)</FieldLabel>
                      <Input
                        id="kb-overlap"
                        type="number"
                        min={0}
                        max={500}
                        value={chunkOverlap}
                        onChange={(e) => setChunkOverlap(Number(e.target.value))}
                      />
                    </Field>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 pt-4 border-t">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setOpenAddSheet(false)}
                    disabled={creating}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={creating || !kbName.trim()}>
                    {creating ? <Spinner className="size-4 mr-1.5" /> : null}
                    Create Collection
                  </Button>
                </div>
              </form>
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2].map((n) => (
            <Card key={n} className="p-4">
              <Skeleton className="h-5 w-32 mb-2" />
              <Skeleton className="h-4 w-48 mb-4" />
              <Skeleton className="h-8 w-20" />
            </Card>
          ))}
        </div>
      ) : error ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Could not load knowledge bases</EmptyTitle>
            <EmptyDescription>{error}</EmptyDescription>
          </EmptyHeader>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Retry
          </Button>
        </Empty>
      ) : bases.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No knowledge bases configured</EmptyTitle>
            <EmptyDescription>
              Create a knowledge base to ground voice agents with product docs, FAQs, and pricing matrices.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {bases.map((kb) => (
            <Card
              key={kb.id}
              className="group flex flex-col justify-between hover:border-border transition-colors shadow-none"
            >
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex size-8 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Database className="size-4" />
                  </div>
                  <Badge variant="outline" className="text-[11px] font-mono font-normal">
                    pgvector
                  </Badge>
                </div>
                <CardTitle className="text-sm font-semibold mt-3 group-hover:text-primary transition-colors">
                  {kb.name}
                </CardTitle>
                <CardDescription className="text-xs line-clamp-1 font-mono">
                  Chunk: {kb.config.chunk_size} tokens (overlap: {kb.config.chunk_overlap})
                </CardDescription>
              </CardHeader>
              <CardContent className="pt-0">
                <Button asChild variant="outline" size="sm" className="w-full justify-between text-xs">
                  <Link to={`/knowledge/${kb.id}`}>
                    Manage sources & test search
                    <ChevronRight className="size-3.5 text-muted-foreground" />
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
