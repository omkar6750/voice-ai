import { useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { AdminOnly } from "@/app/access";
import type { components } from "@/generated/api";
import { LoadState, StatusBadge } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResource } from "@/lib/resources";

type Media = components["schemas"]["MediaResponse"];
export function MediaPanel({ connectionId }: { connectionId: string }) {
  const api = useApi();
  const { data, loading, error, reload } = useResource<components["schemas"]["MediaListResponse"]>(
    `/integrations/${connectionId}/media`,
  );
  const [busy, setBusy] = useState(false);
  const [uploadName, setUploadName] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [providerId, setProviderId] = useState("");
  const [importName, setImportName] = useState("");
  const [importType, setImportType] = useState<"image" | "video" | "document" | "audio">("image");
  const [importMime, setImportMime] = useState("image/jpeg");
  const [editTarget, setEditTarget] = useState<Media | null>(null);
  const [editName, setEditName] = useState("");
  async function upload(file: File) {
    const body = new FormData();
    body.set("file", file);
    if (uploadName.trim()) body.set("display_name", uploadName.trim());
    setBusy(true);
    try {
      await api(`/integrations/${connectionId}/media/upload`, {
        method: "POST",
        body,
      });
      toast.success("Media uploaded to WhatsApp");
      setUploadName("");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Media upload failed",
      );
    } finally {
      setBusy(false);
    }
  }
  async function importMedia() {
    if (!providerId.trim() || !importName.trim()) return;
    setImportBusy(true);
    try {
      await api(`/integrations/${connectionId}/media/import`, {
        method: "POST",
        body: JSON.stringify({
          provider_media_id: providerId.trim(),
          display_name: importName.trim(),
          media_type: importType,
          mime_type: importMime.trim() || "application/octet-stream",
        }),
      });
      toast.success("Existing Meta media added to the catalog");
      setImportOpen(false);
      setProviderId("");
      setImportName("");
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not import media");
    } finally {
      setImportBusy(false);
    }
  }
  async function verify(item: Media) {
    try {
      await api(`/integrations/${connectionId}/media/${item.id}/verify`, { method: "POST" });
      toast.success(`${item.display_name} verified with Meta`);
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Media verification failed");
    }
  }
  async function saveName() {
    if (!editTarget || !editName.trim()) return;
    try {
      await api(`/integrations/${connectionId}/media/${editTarget.id}`, {
        method: "PATCH",
        body: JSON.stringify({ display_name: editName.trim() }),
      });
      toast.success("Media metadata updated");
      setEditTarget(null);
      await reload();
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not update media metadata");
    }
  }
  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Media catalog</h2>
          <p className="text-xs text-muted-foreground">
            Local record of WhatsApp media IDs. Source files uploaded here are
            retained separately from call audio.
          </p>
        </div>
        <AdminOnly><div className="flex flex-wrap gap-2">
          <Input
            className="max-w-56"
            value={uploadName}
            onChange={(event) => setUploadName(event.target.value)}
            placeholder="Display name (optional)"
            aria-label="Uploaded media display name"
          />
          <label className="inline-flex cursor-pointer items-center rounded-md border px-3 py-2 text-sm hover:bg-accent">
            {busy ? "Uploading…" : "Upload media"}
            <Input
              className="sr-only"
              type="file"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
                event.target.value = "";
              }}
            />
          </label>
          <Button type="button" variant="outline" onClick={() => setImportOpen(true)}>
            Add existing Meta ID
          </Button>
        </div></AdminOnly>
      </div>
      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.media.length === 0
            ? "No locally known media IDs yet."
            : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Display name</TableHead>
              <TableHead>Provider ID</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.media.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.display_name}</TableCell>
                <TableCell className="font-mono text-xs">
                  {item.provider_media_id}
                </TableCell>
                <TableCell>{item.media_type} · {item.mime_type}</TableCell>
                <TableCell>{item.source}</TableCell>
                <TableCell>
                  <StatusBadge value={item.status} />
                </TableCell>
                <TableCell className="text-right">
                  <AdminOnly><div className="flex justify-end gap-1">
                    <Button type="button" size="sm" variant="ghost" onClick={() => void verify(item)} disabled={item.status === "available" && item.last_verified_at !== null}>Verify</Button>
                    <Button type="button" size="sm" variant="ghost" onClick={() => { setEditTarget(item); setEditName(item.display_name); }}>Edit</Button>
                  </div></AdminOnly>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
      <AdminOnly><Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add existing Meta media</DialogTitle>
            <DialogDescription>Import a provider media ID already uploaded to this WhatsApp connection.</DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <Field><FieldLabel htmlFor="provider-media-id">Meta media ID</FieldLabel><Input id="provider-media-id" value={providerId} onChange={(event) => setProviderId(event.target.value)} placeholder="1234567890" /></Field>
            <Field><FieldLabel htmlFor="media-display-name">Display name</FieldLabel><Input id="media-display-name" value={importName} onChange={(event) => setImportName(event.target.value)} placeholder="Proposal brochure" /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field><FieldLabel htmlFor="media-type">Media type</FieldLabel><NativeSelect id="media-type" value={importType} onChange={(event) => setImportType(event.target.value as typeof importType)}>{(["image", "video", "document", "audio"] as const).map((type) => <NativeSelectOption key={type} value={type}>{type}</NativeSelectOption>)}</NativeSelect></Field>
              <Field><FieldLabel htmlFor="media-mime">MIME type</FieldLabel><Input id="media-mime" value={importMime} onChange={(event) => setImportMime(event.target.value)} /></Field>
            </div>
          </FieldGroup>
          <DialogFooter><Button type="button" variant="outline" onClick={() => setImportOpen(false)}>Cancel</Button><Button type="button" disabled={importBusy || !providerId.trim() || !importName.trim()} onClick={() => void importMedia()}>{importBusy ? "Adding…" : "Add media"}</Button></DialogFooter>
        </DialogContent>
      </Dialog></AdminOnly>
      <AdminOnly><Dialog open={Boolean(editTarget)} onOpenChange={(open) => { if (!open) setEditTarget(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit media metadata</DialogTitle><DialogDescription>Only the local display name changes; the Meta media ID remains immutable.</DialogDescription></DialogHeader>
          <Field><FieldLabel htmlFor="edit-media-name">Display name</FieldLabel><Input id="edit-media-name" value={editName} onChange={(event) => setEditName(event.target.value)} /></Field>
          <DialogFooter><Button type="button" variant="outline" onClick={() => setEditTarget(null)}>Cancel</Button><Button type="button" disabled={!editName.trim()} onClick={() => void saveName()}>Save</Button></DialogFooter>
        </DialogContent>
      </Dialog></AdminOnly>
    </section>
  );
}
