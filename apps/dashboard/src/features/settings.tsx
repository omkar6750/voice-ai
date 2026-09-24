import { useEffect, useState } from "react";
import { useApi } from "../app/api";
import { Button, Field, Input, Island, Notice } from "../components/ui";

type Workspace = {
  recording_retention_days: number;
  pipeline_log_retention_days: number;
  pipeline_logs_enabled: boolean;
  automatic_callbacks_enabled: boolean;
  callback_due_window_minutes: number;
};
type State = { revision: number; config: Workspace };

export function SettingsPage() {
  const api = useApi();
  const [saved, setSaved] = useState<State | null>(null);
  const [draft, setDraft] = useState<Workspace | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<State>("/workspace")
      .then((data) => {
        setSaved(data);
        setDraft(structuredClone(data.config));
      })
      .catch((cause) =>
        setError(
          cause instanceof Error ? cause.message : "Could not load settings",
        ),
      );
  }, [api]);
  async function save() {
    if (!saved || !draft) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<State>("/workspace", {
        method: "PATCH",
        body: JSON.stringify({ revision: saved.revision, config: draft }),
      });
      setSaved(result);
      setDraft(structuredClone(result.config));
      setNotice("Workspace settings saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }
  const numberField = (
    key:
      | "recording_retention_days"
      | "pipeline_log_retention_days"
      | "callback_due_window_minutes",
    label: string,
  ) =>
    draft && (
      <Field label={label}>
        <Input
          type="number"
          min={1}
          value={draft[key]}
          onChange={(event) =>
            setDraft({ ...draft, [key]: Number(event.target.value) })
          }
        />
      </Field>
    );
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-primary">Workspace</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Settings
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Retention, debugging and automatic callback policy.
          </p>
        </div>
        <Button
          disabled={
            !draft ||
            busy ||
            JSON.stringify(saved?.config) === JSON.stringify(draft)
          }
          onClick={save}
        >
          Save changes
        </Button>
      </div>
      {error && <Notice text={error} error />}
      {notice && <Notice text={notice} />}
      {!draft ? (
        <p className="text-sm text-muted-foreground">Loading settings…</p>
      ) : (
        <>
          <Island
            title="Recordings and logs"
            description="Expiration defaults for call artifacts."
          >
            <div className="grid gap-4 md:grid-cols-2">
              {numberField(
                "recording_retention_days",
                "Recording retention (days)",
              )}
              {numberField(
                "pipeline_log_retention_days",
                "Pipeline log retention (days)",
              )}
            </div>
            <label className="mt-5 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-primary"
                checked={draft.pipeline_logs_enabled}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    pipeline_logs_enabled: event.target.checked,
                  })
                }
              />
              Enable pipeline logs by default
            </label>
          </Island>
          <Island
            title="Callback policy"
            description="Automatic callback launching is off unless enabled here."
          >
            <div className="max-w-sm">
              {numberField(
                "callback_due_window_minutes",
                "Due window (minutes)",
              )}
            </div>
            <label className="mt-5 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="accent-primary"
                checked={draft.automatic_callbacks_enabled}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    automatic_callbacks_enabled: event.target.checked,
                  })
                }
              />
              Launch confirmed callbacks automatically
            </label>
          </Island>
        </>
      )}
    </div>
  );
}
