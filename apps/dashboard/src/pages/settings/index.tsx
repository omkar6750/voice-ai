import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useResource } from "@/lib/resources";

type WorkspaceConfig = {
  recording_retention_days: number;
  pipeline_log_retention_days: number;
  pipeline_logs_enabled: boolean;
  automatic_callbacks_enabled: boolean;
  callback_due_window_minutes: number;
};
type Workspace = { revision: number; config: WorkspaceConfig };
export function SettingsPage() {
  const api = useApi();
  const { data, loading, error, reload } = useResource<Workspace>("/workspace");
  const [config, setConfig] = useState<WorkspaceConfig | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (data) setConfig(data.config);
  }, [data]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!data || !config) return;
    setBusy(true);
    try {
      await api("/workspace", {
        method: "PATCH",
        body: JSON.stringify({ revision: data.revision, config }),
      });
      toast.success("Workspace settings saved");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not save settings",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title="Settings"
        description="Single-workspace retention, logging and callback policy."
      />
      <LoadState loading={loading} error={error}>
        {config && (
          <form onSubmit={save} className="flex max-w-2xl flex-col gap-6">
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="recording-days">
                  Recording retention, days
                </FieldLabel>
                <Input
                  id="recording-days"
                  type="number"
                  min={1}
                  value={config.recording_retention_days}
                  onChange={(event) =>
                    setConfig({
                      ...config,
                      recording_retention_days: Number(event.target.value),
                    })
                  }
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="log-days">
                  Pipeline log retention, days
                </FieldLabel>
                <Input
                  id="log-days"
                  type="number"
                  min={1}
                  value={config.pipeline_log_retention_days}
                  onChange={(event) =>
                    setConfig({
                      ...config,
                      pipeline_log_retention_days: Number(event.target.value),
                    })
                  }
                  required
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="logs-enabled">
                  Pipeline logs by default
                </FieldLabel>
                <NativeSelect
                  id="logs-enabled"
                  value={String(config.pipeline_logs_enabled)}
                  onChange={(event) =>
                    setConfig({
                      ...config,
                      pipeline_logs_enabled: event.target.value === "true",
                    })
                  }
                >
                  <option value="false">Disabled</option>
                  <option value="true">Enabled</option>
                </NativeSelect>
                <FieldDescription>
                  Agent version can override with inherit, enabled or disabled.
                </FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor="auto-callbacks">
                  Automatic callbacks
                </FieldLabel>
                <NativeSelect
                  id="auto-callbacks"
                  value={String(config.automatic_callbacks_enabled)}
                  onChange={(event) =>
                    setConfig({
                      ...config,
                      automatic_callbacks_enabled:
                        event.target.value === "true",
                    })
                  }
                >
                  <option value="false">Disabled</option>
                  <option value="true">Enabled</option>
                </NativeSelect>
                <FieldDescription>
                  Turning this on changes policy. Automatic dispatch worker
                  status needs separate verification.
                </FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor="callback-window">
                  Callback due window, minutes
                </FieldLabel>
                <Input
                  id="callback-window"
                  type="number"
                  min={1}
                  value={config.callback_due_window_minutes}
                  onChange={(event) =>
                    setConfig({
                      ...config,
                      callback_due_window_minutes: Number(event.target.value),
                    })
                  }
                  required
                />
              </Field>
            </FieldGroup>
            <Button type="submit" disabled={busy} className="self-start">
              {busy ? "Saving…" : "Save settings"}
            </Button>
          </form>
        )}
      </LoadState>
    </PageBody>
  );
}
