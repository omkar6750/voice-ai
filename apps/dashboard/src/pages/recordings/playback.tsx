import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/react";
import { FileAudio } from "lucide-react";
import { toast } from "sonner";
import { requestBlob, useSupportSession } from "@/app/api";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { components } from "@/generated/api";

export function RecordingPlayback({ artifact }: { artifact: components["schemas"]["RecordingResponse"] }) {
  const { getToken, orgId } = useAuth();
  const support = useSupportSession();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const blocked = Boolean(support || artifact.deleted_at || artifact.deletion_requested_at ||
    artifact.storage_status !== "available" || (artifact.expires_at && Date.parse(artifact.expires_at) <= Date.now()));
  useEffect(() => {
    generation.current += 1;
    setUrl(null);
    setBusy(false);
    return () => { generation.current += 1; };
  }, [orgId, support, artifact.id, blocked]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  async function load() {
    const current = generation.current;
    setBusy(true);
    try {
      const token = await getToken();
      if (!token) throw new Error("Sign in required");
      const blob = await requestBlob(token, `/artifacts/${artifact.id}/file`);
      if (generation.current === current) setUrl(URL.createObjectURL(blob));
    } catch (cause) {
      if (generation.current === current) toast.error(cause instanceof Error ? cause.message : "Recording unavailable");
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }
  return <div className="flex flex-col gap-2 py-2">
    <span className="text-sm">{artifact.kind === "input" ? "Caller" : artifact.kind === "output" ? "Agent" : "Mixed"} audio · {Math.round((artifact.size_bytes ?? 0) / 1024)} KB</span>
    {blocked ? <p className="text-xs text-muted-foreground">{support ? "Recording access unavailable in support mode." : artifact.deletion_requested_at || artifact.deleted_at ? "Recording deleted or deletion pending." : `Recording ${artifact.storage_status}.`}</p>
      : url ? <audio controls preload="metadata" src={url} className="w-full" />
      : <Button variant="outline" size="sm" disabled={busy} onClick={() => void load()}>
        {busy ? <Spinner data-icon="inline-start" /> : <FileAudio data-icon="inline-start" />}
        {busy ? "Loading…" : "Load recording"}
      </Button>}
  </div>;
}
