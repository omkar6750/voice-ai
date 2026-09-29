import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi, useSupportSession } from "@/app/api";
import { useOrganizationAccess } from "@/app/access";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { components } from "@/generated/api";
import { RecordingPlayback } from "./playback";

type Selection = components["schemas"]["RecordingDeletionSelection"];
type Preview = components["schemas"]["RecordingDeletionPreviewResponse"];
type Operation = components["schemas"]["RecordingDeletionResponse"];
type Catalog = components["schemas"]["RecordingListResponse"];

export function RecordingsPage() {
  const { orgId } = useAuth();
  const support = useSupportSession();
  if (support) return <Alert className="m-6"><AlertTitle>Recording access unavailable</AlertTitle><AlertDescription>Exit support mode to access your organization’s recordings.</AlertDescription></Alert>;
  return <RecordingWorkspace key={orgId} />;
}

function RecordingWorkspace() {
  const api = useApi();
  const { canManage } = useOrganizationAccess();
  const [params, setParams] = useSearchParams();
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [scope, setScope] = useState<Selection["scope"]>("artifacts");
  const [ids, setIds] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [operations, setOperations] = useState<Operation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setCatalog(null);
    void api<Catalog>(`/recordings?offset=${offset}&limit=50`).then(value => {
      if (active) { setCatalog(value); setError(""); }
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "Recordings unavailable"); });
    if (canManage) void api<components["schemas"]["RecordingDeletionListResponse"]>("/recording-deletions")
      .then(value => { if (active) setOperations(value.operations); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "Deletion history unavailable"); });
    return () => { active = false; };
  }, [api, offset, canManage, refresh]);
  async function run(action: () => Promise<void>) {
    setBusy(true);
    try { await action(); } catch (cause) { toast.error(cause instanceof Error ? cause.message : "Recording action failed"); }
    finally { setBusy(false); }
  }
  async function prepare() {
    const body: Selection = scope === "artifacts" ? { scope, ids: [...selected] }
      : scope === "runs" || scope === "calls" ? { scope, ids: ids.split(/[\s,]+/).filter(Boolean) }
      : scope === "utc_range" ? { scope, start, end } : { scope };
    const value = await api<Preview>("/recording-deletions/preview", { method: "POST", body: JSON.stringify(body) });
    setConfirmation(""); setPreview(value);
  }
  async function execute() {
    if (!preview) return;
    await api<Operation>(`/recording-deletions/${preview.operation_id}/execute`, { method: "POST", body: JSON.stringify({ confirmation_token: preview.confirmation_token, confirmation_text: confirmation }) });
    setPreview(null); setSelected(new Set()); setRefresh(value => value + 1);
    toast.success("Recording access blocked. Continue deletion below.");
  }
  return <div className="flex flex-col gap-5 p-6">
    <div className="flex items-center justify-between gap-3"><h1 className="text-xl font-semibold">Recordings</h1><Button variant="outline" disabled={busy} onClick={() => setRefresh(value => value + 1)}>Refresh</Button></div>
    <p className="text-sm text-muted-foreground">New recordings remain until manually deleted. Older explicit expiry dates still apply. Deletion never runs in the background.</p>
    {error && <Alert variant="destructive"><AlertTitle>Recordings unavailable</AlertTitle><AlertDescription>{error}</AlertDescription></Alert>}
    {catalog?.artifacts.some(row => row.storage_status === "failed") && <Alert><AlertTitle>Recording upload needs attention</AlertTitle><AlertDescription>Some recordings have unconfirmed uploads. Their audio is unavailable until runtime registration is retried.</AlertDescription></Alert>}
    <Table><TableHeader><TableRow>{canManage && <TableHead>Select</TableHead>}<TableHead>Run / recording</TableHead><TableHead>Created (UTC)</TableHead><TableHead>Status</TableHead><TableHead>Playback</TableHead></TableRow></TableHeader>
      <TableBody>{catalog?.artifacts.map(row => <TableRow key={row.id}>
        {canManage && <TableCell><Checkbox aria-label={`Select recording ${row.id}`} disabled={busy || Boolean(row.deleted_at || row.deletion_requested_at) || row.storage_status === "uploading"} checked={selected.has(row.id)} onCheckedChange={checked => setSelected(previous => { const next = new Set(previous); if (checked) next.add(row.id); else next.delete(row.id); return next; })} /></TableCell>}
        <TableCell><Link to={`/runs/${row.run_id}`}>{row.run_id.slice(0, 8)} · {row.kind}</Link><p className="text-xs text-muted-foreground">{row.id}</p></TableCell>
        <TableCell>{new Date(row.created_at).toISOString()}</TableCell><TableCell><Badge variant="secondary">{row.storage_status}</Badge>{row.deletion_error && <p>{row.deletion_error}</p>}</TableCell><TableCell><RecordingPlayback artifact={row} /></TableCell>
      </TableRow>)}{catalog?.artifacts.length === 0 && <TableRow><TableCell colSpan={canManage ? 5 : 4}>No recordings on this page.</TableCell></TableRow>}</TableBody></Table>
    <div className="flex items-center gap-3"><Button variant="outline" disabled={offset === 0 || busy} onClick={() => setParams({ offset: String(Math.max(0, offset - 50)) })}>Previous</Button><span className="text-sm">{catalog ? `${catalog.total} total · ${selected.size} selected across pages` : "Loading…"}</span><Button variant="outline" disabled={!catalog || offset + 50 >= catalog.total || busy} onClick={() => setParams({ offset: String(offset + 50) })}>Next</Button>{canManage && <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear selection</Button>}</div>
    {canManage && <>
      <FieldGroup>
        <Field><FieldLabel htmlFor="recording-scope">Delete recordings belonging to</FieldLabel><NativeSelect id="recording-scope" value={scope} onChange={event => setScope(event.target.value as Selection["scope"])}>
          <NativeSelectOption value="artifacts">Selected recordings across pages</NativeSelectOption><NativeSelectOption value="runs">Selected run IDs</NativeSelectOption><NativeSelectOption value="calls">Selected call IDs</NativeSelectOption><NativeSelectOption value="utc_range">Run creation UTC range</NativeSelectOption><NativeSelectOption value="all_current_org">All current organization recordings</NativeSelectOption>
        </NativeSelect><FieldDescription>The server previews the exact eligible set. Active runs and uploading recordings are excluded.</FieldDescription></Field>
        {(scope === "runs" || scope === "calls") && <Field><FieldLabel htmlFor="recording-ids">{scope === "runs" ? "Run" : "Call"} IDs</FieldLabel><Input id="recording-ids" value={ids} onChange={event => setIds(event.target.value)} placeholder="Comma or space separated IDs" /></Field>}
        {scope === "utc_range" && <><Field><FieldLabel htmlFor="recording-start">From UTC (inclusive)</FieldLabel><Input id="recording-start" value={start} onChange={event => setStart(event.target.value)} placeholder="2026-09-29T00:00:00Z" /></Field><Field><FieldLabel htmlFor="recording-end">Until UTC (exclusive)</FieldLabel><Input id="recording-end" value={end} onChange={event => setEnd(event.target.value)} placeholder="2026-09-30T00:00:00Z" /></Field></>}
      </FieldGroup>
      <Button variant="destructive" disabled={busy || (scope === "artifacts" && selected.size === 0)} onClick={() => void run(prepare)}>Preview deletion</Button>
      <AlertDialog open={Boolean(preview)} onOpenChange={open => { if (!open && !busy) setPreview(null); }}><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Confirm recording deletion</AlertDialogTitle><AlertDialogDescription>{preview?.artifact_ids.length} recordings · {Math.round((preview?.size_bytes ?? 0) / 1024)} KB. {preview?.excluded} excluded. Confirmation expires at {preview?.expires_at}. Audio access will be blocked immediately.</AlertDialogDescription></AlertDialogHeader>
        <div className="max-h-40 overflow-auto"><ul>{preview?.artifact_ids.map(id => <li key={id} className="break-all text-xs">{id}</li>)}</ul></div>
        <FieldGroup><Field><FieldLabel htmlFor="recording-confirm">Type {preview?.confirmation_text}</FieldLabel><Input id="recording-confirm" value={confirmation} onChange={event => setConfirmation(event.target.value)} autoComplete="off" /></Field></FieldGroup>
        <AlertDialogFooter><AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={busy || !preview?.artifact_ids.length || confirmation !== preview.confirmation_text} onClick={event => { event.preventDefault(); void run(execute); }}>Block access and delete</AlertDialogAction></AlertDialogFooter>
      </AlertDialogContent></AlertDialog>
      <h2 className="text-lg font-semibold">Manual deletion progress</h2>
      {operations.length === 0 && <p className="text-sm text-muted-foreground">No confirmed deletion operations.</p>}
      {operations.map(operation => <div key={operation.id} className="flex flex-col gap-2 border-b py-3"><div className="flex items-center gap-3"><Badge variant="secondary">{operation.status}</Badge><span className="text-sm">{operation.deleted}/{operation.total} deleted · {operation.failed} failed · {operation.pending} pending</span><Button variant="outline" disabled={busy || operation.status === "completed"} onClick={() => void run(async () => { await api<Operation>(`/recording-deletions/${operation.id}/continue`, { method: "POST" }); setRefresh(value => value + 1); })}>Continue / retry up to 100</Button></div>{operation.items.filter(item => item.error).map(item => <p key={item.artifact_id} className="text-xs text-muted-foreground">{item.artifact_id}: {item.error}</p>)}</div>)}
    </>}
  </div>;
}
