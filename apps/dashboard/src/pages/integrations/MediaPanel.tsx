import { useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { LoadState, StatusBadge } from "@/components/record-page";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResource } from "@/lib/resources";

type Media = {
  id: string;
  provider_media_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  availability: string;
};
export function MediaPanel({ connectionId }: { connectionId: string }) {
  const api = useApi();
  const { data, loading, error, reload } = useResource<{ media: Media[] }>(
    `/integrations/${connectionId}/media`,
  );
  const [busy, setBusy] = useState(false);
  async function upload(file: File) {
    const body = new FormData();
    body.set("file", file);
    setBusy(true);
    try {
      await api(`/integrations/${connectionId}/media/upload`, {
        method: "POST",
        body,
      });
      toast.success("Media uploaded to WhatsApp");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Media upload failed",
      );
    } finally {
      setBusy(false);
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
              <TableHead>File</TableHead>
              <TableHead>Provider ID</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.media.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium">{item.filename}</TableCell>
                <TableCell className="font-mono text-xs">
                  {item.provider_media_id}
                </TableCell>
                <TableCell>{item.mime_type}</TableCell>
                <TableCell>
                  <StatusBadge value={item.availability} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
    </section>
  );
}
