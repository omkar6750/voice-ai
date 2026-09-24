import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CheckCircle, Radio, RefreshCw, ShieldAlert, Signal } from "lucide-react";
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

interface EndpointItem {
  id: string;
  name: string;
  config: {
    provider: string;
    at_port: string;
    audio_port: string;
    baudrate: number;
    sample_rates: number[];
    at_timeout_secs: number;
  };
  created_at: string;
}

export function EndpointsPage() {
  const api = useApi();
  const [endpoints, setEndpoints] = useState<EndpointItem[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = await api<{ endpoints: EndpointItem[] }>("/runtime-endpoints");
      setEndpoints(data.endpoints);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load runtime endpoints");
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
          <h1 className="text-xl font-semibold tracking-tight">Runtime Endpoints & Telephony</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Hardware modems, SIM7600 serial COM ports, USB audio bridges, and lease locks.
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
          <Skeleton className="h-28 w-full" />
        </Card>
      ) : endpoints.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No runtime endpoints registered</EmptyTitle>
            <EmptyDescription>
              Register a hardware modem or SIP gateway endpoint to start making cellular VoLTE calls.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {endpoints.map((ep) => (
            <Card key={ep.id} className="shadow-none flex flex-col justify-between">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Radio className="size-4" />
                    </div>
                    <div>
                      <CardTitle className="text-sm font-semibold">{ep.name}</CardTitle>
                      <CardDescription className="text-xs font-mono uppercase">
                        {ep.config.provider} · ID: {ep.id.slice(0, 8)}…
                      </CardDescription>
                    </div>
                  </div>
                  <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[11px]">
                    ● Idle / Ready
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="pt-0 flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-2 rounded-md border p-3 bg-muted/20 text-xs font-mono">
                  <div>
                    <span className="text-[10px] uppercase text-muted-foreground block">AT Port</span>
                    <span className="font-semibold text-foreground">{ep.config.at_port}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase text-muted-foreground block">Audio Port</span>
                    <span className="font-semibold text-foreground">{ep.config.audio_port}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase text-muted-foreground block">Baudrate</span>
                    <span className="text-foreground">{ep.config.baudrate}</span>
                  </div>
                  <div>
                    <span className="text-[10px] uppercase text-muted-foreground block">PCM Rate</span>
                    <span className="text-foreground">{(ep.config.sample_rates || [16000]).join(", ")} Hz</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
