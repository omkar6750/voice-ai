import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

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
  const [bases, setBases] = useState<KBItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
