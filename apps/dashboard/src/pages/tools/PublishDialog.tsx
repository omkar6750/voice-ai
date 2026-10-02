import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CopyId } from "./workspace";

type Candidate = { id: string; version: number; revision: number };
type Validation = components["schemas"]["ToolValidationResponse"];

export function PublishDialog({
  candidate,
  close,
  onPublished,
}: {
  candidate: Candidate | null;
  close: () => void;
  onPublished: () => Promise<void>;
}) {
  const api = useApi();
  const [validation, setValidation] = useState<Validation | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const publishing = useRef(false);
  useEffect(() => {
    setValidation(null);
    setError("");
    if (!candidate) return;
    const controller = new AbortController();
    void api<Validation>(`/tool-versions/${candidate.id}/validate`, {
      method: "POST",
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) setValidation(result);
      })
      .catch((cause: Error) => {
        if (!controller.signal.aborted) setError(cause.message);
      });
    return () => controller.abort();
  }, [candidate, api]);
  const valid =
    validation?.valid &&
    validation.id === candidate?.id &&
    validation.revision === candidate?.revision;
  async function publish() {
    if (!candidate || !valid || publishing.current) return;
    publishing.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`/tool-versions/${candidate.id}/publish`, {
        method: "POST",
        body: JSON.stringify({ revision: validation!.revision }),
      });
      toast.success(`Version ${candidate.version} published`);
      close();
      await onPublished();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not publish version",
      );
    } finally {
      publishing.current = false;
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={Boolean(candidate)}
      onOpenChange={(open) => {
        if (!open && !busy) close();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Publish v{candidate?.version}</DialogTitle>
          <DialogDescription>
            This saved revision becomes immutable. Existing agent bindings keep
            their pinned versions.
          </DialogDescription>
        </DialogHeader>
        {candidate && <CopyId label="Version ID" value={candidate.id} />}
        <p className="text-sm">Saved revision {candidate?.revision}</p>
        {!validation && !error && (
          <p role="status" className="text-sm text-muted-foreground">
            Validating saved configuration…
          </p>
        )}
        {validation?.config && (
          <div className="flex flex-col gap-2 text-sm">
            <strong>{validation.config.name}</strong>
            <p>{validation.config.description || "No description"}</p>
            <p>
              Execution:{" "}
              {validation.config.handler ??
                validation.config.http?.url ??
                validation.config.kind}
            </p>
          </div>
        )}
        {validation && !valid && (
          <Alert variant="destructive">
            <AlertTitle>Publication blocked</AlertTitle>
            <AlertDescription>
              {validation.revision !== candidate?.revision ? (
                "This draft changed. Close this dialog and refresh before reviewing again."
              ) : (
                <ul>
                  {validation.issues?.map((issue, i) => (
                    <li key={i}>{issue.message}</li>
                  ))}
                </ul>
              )}
            </AlertDescription>
          </Alert>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertTitle>Could not publish</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={close}>
            Cancel
          </Button>
          <Button
            disabled={!valid || busy || Boolean(error)}
            onClick={() => void publish()}
          >
            {busy ? "Publishing…" : "Publish version"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
