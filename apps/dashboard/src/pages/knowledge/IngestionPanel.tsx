import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { ReadOnlyValue } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { KnowledgeBase } from "./types";

export function IngestionPanel({
  base,
  saved,
}: {
  base: KnowledgeBase;
  saved: () => Promise<unknown>;
}) {
  const api = useApi();
  const [name, setName] = useState(base.name);
  const [config, setConfig] = useState(base.config);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`/knowledge-bases/${base.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: name.trim(), config }),
      });
      toast.success("Ingestion settings saved. Existing sources need rebuild.");
      await saved();
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not save ingestion settings",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="flex max-w-2xl flex-col gap-6">
      <div>
        <h2 className="text-base font-semibold">Ingestion settings</h2>
        <p className="text-xs text-muted-foreground">
          Changed settings fence in-flight builds. Rebuild affected sources
          explicitly.
        </p>
      </div>
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="base-name">Name</FieldLabel>
          <Input
            id="base-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={120}
            required
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="chunk-size">Chunk size</FieldLabel>
          <Input
            id="chunk-size"
            type="number"
            min={1}
            value={config.chunk_size}
            onChange={(event) =>
              setConfig({ ...config, chunk_size: Number(event.target.value) })
            }
            required
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="chunk-overlap">Chunk overlap</FieldLabel>
          <Input
            id="chunk-overlap"
            type="number"
            min={0}
            max={config.chunk_size - 1}
            value={config.chunk_overlap}
            onChange={(event) =>
              setConfig({
                ...config,
                chunk_overlap: Number(event.target.value),
              })
            }
            required
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="markdown-aware">
            Markdown-aware splitting
          </FieldLabel>
          <NativeSelect
            id="markdown-aware"
            value={String(config.markdown_aware)}
            onChange={(event) =>
              setConfig({
                ...config,
                markdown_aware: event.target.value === "true",
              })
            }
          >
            <option value="true">Enabled</option>
            <option value="false">Disabled</option>
          </NativeSelect>
        </Field>
        <Field>
          <FieldLabel htmlFor="max-chars">
            Maximum extraction characters
          </FieldLabel>
          <Input
            id="max-chars"
            type="number"
            min={1}
            value={config.extraction_max_chars}
            onChange={(event) =>
              setConfig({
                ...config,
                extraction_max_chars: Number(event.target.value),
              })
            }
            required
          />
        </Field>
      </FieldGroup>
      <div>
        <ReadOnlyValue
          label="Embedding provider"
          value={config.embedding_provider}
        />
        <ReadOnlyValue label="Embedding model" value={config.embedding_model} />
        <ReadOnlyValue label="Dimensions" value={config.embedding_dimensions} />
        <ReadOnlyValue
          label="Normalize vectors"
          value={String(config.normalize_embeddings)}
        />
        <ReadOnlyValue
          label="Supported source kinds"
          value={config.supported_sources.join(", ")}
          reason="Fixed by current ingestion contract."
        />
      </div>
      <Button
        className="self-start"
        type="submit"
        disabled={
          busy || !name.trim() || config.chunk_overlap >= config.chunk_size
        }
      >
        {busy ? "Saving…" : "Save settings"}
      </Button>
    </form>
  );
}
