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
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Card, CardContent } from "@/components/ui/card";
import { MediaPreviewImage } from "./MediaPreviewImage";
import { useResource } from "@/lib/resources";

type Media = components["schemas"]["MediaResponse"];
export function MediaPanel({ connectionId }: { connectionId: string }) {
  const api = useApi();
  const { data, loading, error, reload } = useResource<
    components["schemas"]["MediaListResponse"]
  >(`/integrations/${connectionId}/media`);
  const [busy, setBusy] = useState(false);
  const [uploadName, setUploadName] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importBusy, setImportBusy] = useState(false);
  const [providerId, setProviderId] = useState("");
  const [importName, setImportName] = useState("");
  const [importType, setImportType] = useState<
    "image" | "video" | "document" | "audio"
  >("image");
  const [importMime, setImportMime] = useState("image/jpeg");
  const [editTarget, setEditTarget] = useState<Media | null>(null);
  const [editName, setEditName] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Media | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  async function upload(file: File) {
    if (
      file.size > 5 * 1024 * 1024 ||
      !["image/png", "image/jpeg"].includes(file.type)
    ) {
      toast.error("Choose a PNG or JPEG image under 5 MiB");
      return;
    }
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
      toast.error(
        cause instanceof Error ? cause.message : "Could not import media",
      );
    } finally {
      setImportBusy(false);
    }
  }
  async function verify(item: Media) {
    try {
      await api(`/integrations/${connectionId}/media/${item.id}/verify`, {
        method: "POST",
      });
      toast.success(`${item.display_name} verified with Meta`);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Media verification failed",
      );
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
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not update media metadata",
      );
    }
  }
  async function deleteMedia() {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await api(`/integrations/${connectionId}/media/${deleteTarget.id}`, {
        method: "DELETE",
      });
      toast.success("Meta media and catalog reference deleted");
      setDeleteTarget(null);
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Media deletion failed",
      );
    } finally {
      setDeleteBusy(false);
    }
  }
  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Media catalog</h2>
          <p className="text-xs text-muted-foreground">
            Images upload directly to Meta. This catalog stores provider IDs and
            safe metadata only; no image bytes are retained locally.
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
            {busy ? "Uploading…" : "Upload image"}
            <Input
              className="sr-only"
              type="file"
              accept="image/png,image/jpeg"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void upload(file);
                event.target.value = "";
              }}
            />
          </label>
          <Button
            type="button"
            variant="outline"
            onClick={() => setImportOpen(true)}
          >
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
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {data?.media.map((item) => (
            <Card key={item.id}>
              <CardContent className="flex flex-col gap-3 p-3">
                {item.media_type === "image" && item.status === "available" ? (
                  <MediaPreviewImage
                    connectionId={connectionId}
                    mediaId={item.id}
                    alt={item.display_name}
                  />
                ) : (
                  <div className="flex aspect-video items-center justify-center rounded-md bg-muted text-xs text-muted-foreground">
                    {item.status === "available"
                      ? item.media_type
                      : "Verify media"}
                  </div>
                )}
                <div className="min-w-0 text-xs">
                  <p className="truncate font-medium">{item.display_name}</p>
                  <p className="truncate text-muted-foreground">
                    {item.filename}
                  </p>
                  <p className="break-all font-mono text-muted-foreground">
                    Meta ID: {item.provider_media_id}
                  </p>
                  <p className="text-muted-foreground">
                    {item.mime_type} · {item.size_bytes.toLocaleString()} bytes
                    · {item.status}
                  </p>
                </div>
                <AdminOnly><div className="flex flex-wrap justify-end gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => void verify(item)}
                    disabled={
                      item.status === "available" &&
                      item.last_verified_at !== null
                    }
                  >
                    Verify
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      setEditTarget(item);
                      setEditName(item.display_name);
                    }}
                  >
                    Edit metadata
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="destructive"
                    onClick={() => setDeleteTarget(item)}
                  >
                    Delete from Meta
                  </Button>
                </div></AdminOnly>
              </CardContent>
            </Card>
          ))}
        </div>
      </LoadState>
      <AdminOnly><Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add existing Meta media</DialogTitle>
            <DialogDescription>
              Import a provider media ID already uploaded to this WhatsApp
              connection.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="provider-media-id">Meta media ID</FieldLabel>
              <Input
                id="provider-media-id"
                value={providerId}
                onChange={(event) => setProviderId(event.target.value)}
                placeholder="1234567890"
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="media-display-name">Display name</FieldLabel>
              <Input
                id="media-display-name"
                value={importName}
                onChange={(event) => setImportName(event.target.value)}
                placeholder="Proposal brochure"
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="media-type">Media type</FieldLabel>
                <NativeSelect
                  id="media-type"
                  value={importType}
                  onChange={(event) =>
                    setImportType(event.target.value as typeof importType)
                  }
                >
                  {(["image", "video", "document", "audio"] as const).map(
                    (type) => (
                      <NativeSelectOption key={type} value={type}>
                        {type}
                      </NativeSelectOption>
                    ),
                  )}
                </NativeSelect>
              </Field>
              <Field>
                <FieldLabel htmlFor="media-mime">MIME type</FieldLabel>
                <Input
                  id="media-mime"
                  value={importMime}
                  onChange={(event) => setImportMime(event.target.value)}
                />
              </Field>
            </div>
          </FieldGroup>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setImportOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={importBusy || !providerId.trim() || !importName.trim()}
              onClick={() => void importMedia()}
            >
              {importBusy ? "Adding…" : "Add media"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(editTarget)}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit media metadata</DialogTitle>
            <DialogDescription>
              Only the local display name changes; the Meta media ID remains
              immutable.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor="edit-media-name">Display name</FieldLabel>
            <Input
              id="edit-media-name"
              value={editName}
              onChange={(event) => setEditName(event.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setEditTarget(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!editName.trim()}
              onClick={() => void saveName()}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !deleteBusy) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Meta media?</DialogTitle>
            <DialogDescription>
              This removes the image from Meta and the local metadata catalog.
              Deletion is blocked while a tool version or executable run still
              references it.
            </DialogDescription>
          </DialogHeader>
          <p className="break-all font-mono text-xs">
            {deleteTarget?.provider_media_id}
          </p>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={deleteBusy}
              onClick={() => setDeleteTarget(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deleteBusy}
              onClick={() => void deleteMedia()}
            >
              {deleteBusy ? "Deleting…" : "Delete media"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog></AdminOnly>
    </section>
  );
}
