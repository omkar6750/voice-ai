import { useEffect, useState } from "react";
import { Check, RefreshCw, Save, Settings2, ShieldCheck } from "lucide-react";
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
import { Skeleton } from "@/components/ui/skeleton";

interface WorkspaceData {
  revision: number;
  config: {
    automatic_callbacks_enabled: boolean;
    callback_due_window_minutes: number;
    recording_retention_days: number;
    pipeline_log_retention_days: number;
    pipeline_logs_enabled: boolean;
  };
}

export function SettingsPage() {
  const api = useApi();
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const res = await api<WorkspaceData>("/workspace");
      setData(res);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function save() {
    if (!data) return;
    setSaving(true);
    try {
      const res = await api<WorkspaceData>("/workspace", {
        method: "PATCH",
        body: JSON.stringify({
          revision: data.revision,
          config: data.config,
        }),
      });
      setData(res);
      toast.success("Workspace settings updated");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-4xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Workspace Settings</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Retention policies, automatic callbacks, and pipeline telemetry overrides.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-3.5 mr-1.5" /> Refresh
          </Button>
          <Button size="sm" onClick={() => void save()} disabled={saving || !data}>
            <Save className="size-3.5 mr-1.5" />
            {saving ? "Saving…" : "Save Changes"}
          </Button>
        </div>
      </div>

      {loading || !data ? (
        <Card className="p-6">
          <Skeleton className="h-6 w-48 mb-4" />
          <Skeleton className="h-32 w-full" />
        </Card>
      ) : (
        <div className="flex flex-col gap-4">
          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Retention & Privacy</CardTitle>
              <CardDescription className="text-xs">
                Automatic purging of call audio recordings and raw pipeline logs.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium">Recording Audio Retention (Days)</label>
                  <Input
                    type="number"
                    min="1"
                    max="365"
                    value={data.config.recording_retention_days}
                    onChange={(e) =>
                      setData({
                        ...data,
                        config: {
                          ...data.config,
                          recording_retention_days: parseInt(e.target.value) || 7,
                        },
                      })
                    }
                    className="text-xs h-8 font-mono"
                  />
                  <span className="text-[11px] text-muted-foreground">
                    Number of days full-call audio artifacts are retained before deletion.
                  </span>
                </div>

                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium">Pipeline Log Retention (Days)</label>
                  <Input
                    type="number"
                    min="1"
                    max="365"
                    value={data.config.pipeline_log_retention_days}
                    onChange={(e) =>
                      setData({
                        ...data,
                        config: {
                          ...data.config,
                          pipeline_log_retention_days: parseInt(e.target.value) || 7,
                        },
                      })
                    }
                    className="text-xs h-8 font-mono"
                  />
                  <span className="text-[11px] text-muted-foreground">
                    Retention window for debug trace logs.
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="shadow-none">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Automatic Callbacks</CardTitle>
              <CardDescription className="text-xs">
                Background dispatcher behavior for requested callback appointments.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-xs font-medium">Callback Due Window (Minutes)</label>
                  <Input
                    type="number"
                    min="1"
                    max="60"
                    value={data.config.callback_due_window_minutes}
                    onChange={(e) =>
                      setData({
                        ...data,
                        config: {
                          ...data.config,
                          callback_due_window_minutes: parseInt(e.target.value) || 15,
                        },
                      })
                    }
                    className="text-xs h-8 font-mono"
                  />
                  <span className="text-[11px] text-muted-foreground">
                    Acceptable time window around the due date to launch automatic callbacks.
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
