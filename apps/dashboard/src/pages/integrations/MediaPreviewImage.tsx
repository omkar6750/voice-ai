import { useEffect, useState } from "react";
import { requestBlob, useOperatorToken } from "@/app/api";

export function MediaPreviewImage({
  connectionId,
  mediaId,
  alt,
}: {
  connectionId: string;
  mediaId: string;
  alt: string;
}) {
  const token = useOperatorToken();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setUrl(null);
    setFailed(false);
    void requestBlob(
      token,
      `/integrations/${connectionId}/media/${mediaId}/preview`,
    )
      .then((blob) => {
        if (!blob.type.startsWith("image/"))
          throw new Error("Invalid image preview type");
        if (active) {
          objectUrl = URL.createObjectURL(blob);
          setUrl(objectUrl);
        }
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [connectionId, mediaId, token]);

  if (failed)
    return (
      <div className="flex aspect-video items-center justify-center bg-muted text-xs text-muted-foreground">
        Preview unavailable
      </div>
    );
  if (!url)
    return (
      <div className="flex aspect-video items-center justify-center bg-muted text-xs text-muted-foreground">
        Loading preview…
      </div>
    );
  return (
    <img
      src={url}
      alt={alt}
      className="aspect-video w-full rounded-md object-contain bg-muted"
    />
  );
}
