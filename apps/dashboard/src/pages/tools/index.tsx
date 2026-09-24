import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Cpu, Layers, ListTodo, RefreshCw, Sparkles, Wrench } from "lucide-react";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface ToolItem {
  id: string;
  name: string;
}

interface ToolVersionDetail {
  id: string;
  version: number;
  status: string;
  config: {
    name: string;
    description: string;
    parameters: any;
    handler: string;
  };
}

interface ProviderSlot {
  provider: string;
  slots: string[];
  models: string[];
}

export function ToolsPage() {
  const api = useApi();
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [toolDetails, setToolDetails] = useState<Record<string, ToolVersionDetail>>({});
  const [providers, setProviders] = useState<ProviderSlot[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [toolsData, providersData] = await Promise.all([
        api<{ tools: ToolItem[] }>("/tools"),
        api<{ providers: ProviderSlot[] }>("/providers"),
      ]);
      setTools(toolsData.tools);
      setProviders(providersData.providers);

      // Load latest version for each tool
      const detailsMap: Record<string, ToolVersionDetail> = {};
      await Promise.all(
        toolsData.tools.map(async (t) => {
          try {
            const vData = await api<{ versions: ToolVersionDetail[] }>(`/tools/${t.id}/versions`);
            if (vData.versions.length > 0) {
              detailsMap[t.id] = vData.versions[vData.versions.length - 1];
            }
          } catch {}
        })
      );
      setToolDetails(detailsMap);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load tools and providers");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Tools & AI Provider Registry</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Registered LLM function schemas, tool parameter validators, and active STT, LLM, TTS, and embedding slots.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
        </div>
      </div>

      {loading ? (
        <Card className="p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-32 w-full" />
        </Card>
      ) : (
        <>
          {/* Tools Catalog Table */}
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Wrench className="size-4 text-primary" />
                <CardTitle className="text-sm font-semibold">Registered Tools ({tools.length})</CardTitle>
              </div>
              <CardDescription className="text-xs">
                Executable function schemas bound to conversation flow nodes.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {tools.length === 0 ? (
                <div className="p-6 text-center text-xs text-muted-foreground">No tools registered.</div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Tool Name</TableHead>
                      <TableHead className="text-xs">Description</TableHead>
                      <TableHead className="text-xs">Handler</TableHead>
                      <TableHead className="text-xs text-right">Version</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tools.map((t) => {
                      const detail = toolDetails[t.id];
                      return (
                        <TableRow key={t.id}>
                          <TableCell className="font-mono text-xs font-semibold">
                            {t.name}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground max-w-md">
                            {detail?.config?.description || "—"}
                          </TableCell>
                          <TableCell className="font-mono text-[11px] text-muted-foreground">
                            {detail?.config?.handler || "native"}
                          </TableCell>
                          <TableCell className="text-right">
                            <Badge variant="outline" className="text-[10px] font-mono">
                              v{detail?.version || 1}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* AI Providers & Slot Matrix */}
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Cpu className="size-4 text-primary" />
                <CardTitle className="text-sm font-semibold">AI Provider Slots & Models</CardTitle>
              </div>
              <CardDescription className="text-xs">
                Decoupled pipeline slots mapped to active models.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Provider</TableHead>
                    <TableHead className="text-xs">Pipeline Slots</TableHead>
                    <TableHead className="text-xs">Supported Models</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {providers.map((p) => (
                    <TableRow key={p.provider}>
                      <TableCell className="font-semibold text-xs capitalize">
                        {p.provider}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {p.slots.map((s) => (
                            <Badge key={s} variant="outline" className="uppercase font-mono text-[10px] bg-muted/40">
                              {s}
                            </Badge>
                          ))}
                        </div>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {p.models.join(", ")}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
