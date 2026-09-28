import { useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { components } from "@/generated/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useResource } from "@/lib/resources";
import { MediaPreviewImage } from "./MediaPreviewImage";

type Media = components["schemas"]["MediaResponse"];

export function WhatsAppMediaPicker({
  connectionId,
  selectedProviderId,
  onSelect,
}: {
  connectionId: string;
  selectedProviderId?: string | null;
  onSelect: (providerMediaId: string | null) => void;
}) {
  const api = useApi();
  const { data, loading, reload } = useResource<
    components["schemas"]["MediaListResponse"]
  >(`/integrations/${connectionId}/media`);
  const [busy, setBusy] = useState(false);
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
    setBusy(true);
    try {
      const item = await api<Media>(
        `/integrations/${connectionId}/media/upload`,
        { method: "POST", body },
      );
      onSelect(item.provider_media_id);
      await reload();
      toast.success("Image uploaded to WhatsApp and selected");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Image upload failed",
      );
    } finally {
      setBusy(false);
    }
  }
  const images =
    data?.media.filter((item) => item.media_type === "image") ?? [];
  const selectedIsMissing =
    !loading &&
    Boolean(data) &&
    Boolean(selectedProviderId) &&
    !images.some((item) => item.provider_media_id === selectedProviderId);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-muted-foreground">
          Images are stored by Meta. This catalog keeps only their Meta IDs and
          metadata.
        </p>
        <label className="shrink-0">
          <span className="sr-only">Upload PNG or JPEG image</span>
          <Input
            className="max-w-52"
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
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading images…</p>
      ) : null}
      {selectedIsMissing ? (
        <p role="alert" className="text-sm text-destructive">
          The configured Meta image ID is not available in this connection’s
          image catalog. Select or upload a replacement.
        </p>
      ) : null}
      {!loading && images.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No image references on this WhatsApp connection.
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {images.map((item) => (
          <Card
            key={item.id}
            className={
              selectedProviderId === item.provider_media_id
                ? "border-primary"
                : undefined
            }
          >
            <CardContent className="flex flex-col gap-3 p-3">
              {item.status === "available" ? (
                <MediaPreviewImage
                  connectionId={connectionId}
                  mediaId={item.id}
                  alt={item.display_name}
                />
              ) : (
                <div className="flex aspect-video items-center justify-center rounded-md bg-muted text-xs text-muted-foreground">
                  Verify image to preview
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
                  {item.mime_type} · {item.size_bytes.toLocaleString()} bytes ·{" "}
                  {item.status}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant={
                  selectedProviderId === item.provider_media_id
                    ? "secondary"
                    : "outline"
                }
                disabled={item.status !== "available"}
                aria-pressed={selectedProviderId === item.provider_media_id}
                onClick={() =>
                  onSelect(
                    selectedProviderId === item.provider_media_id
                      ? null
                      : item.provider_media_id,
                  )
                }
              >
                {selectedProviderId === item.provider_media_id
                  ? "Selected · clear"
                  : "Select image"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
