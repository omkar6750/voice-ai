import { useRef, useState } from "react";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "@/components/ui/field";
import type { components } from "@/generated/api";
import type { AgentConfig } from "./types";
type Preview = components["schemas"]["PromptPreviewResponse"];
export function PromptPreview({
  config,
  nodeId,
  versionId,
}: {
  config: AgentConfig;
  nodeId: string;
  versionId: string;
}) {
  const api = useApi(),
    [contact, setContact] = useState<Record<string, string>>({}),
    [facts, setFacts] = useState<Record<string, string | number | boolean>>({});
  const [result, setResult] = useState<Preview | null>(null),
    [error, setError] = useState(""),
    [pending, setPending] = useState(false);
  const signature = JSON.stringify([config, nodeId, versionId, contact, facts]);
  const current = useRef(signature);
  current.current = signature;
  const [resultSignature, setResultSignature] = useState("");
  async function preview(allEmpty = false) {
    const startedSignature = signature;
    setPending(true);
    setError("");
    setResult(null);
    try {
      const response = await api<Preview>(
        `/agent-versions/${versionId}/prompt-preview`,
        {
          method: "POST",
          body: JSON.stringify({
            config,
            node_id: nodeId,
            contact_values: allEmpty
              ? Object.fromEntries(config.contact_variables.map((k) => [k, ""]))
              : Object.fromEntries(
                  Object.entries(contact).filter(([k]) =>
                    config.contact_variables.includes(k),
                  ),
                ),
            fact_values: allEmpty
              ? Object.fromEntries(config.fact_slots.map((s) => [s.key, ""]))
              : Object.fromEntries(
                  Object.entries(facts).filter(([k]) =>
                    config.fact_slots.some((s) => s.key === k),
                  ),
                ),
          }),
        },
      );
      if (current.current === startedSignature) {
        setResult(response);
        setResultSignature(startedSignature);
      }
    } catch (e) {
      if (current.current === startedSignature) setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <FieldGroup>
      <FieldDescription>
        Preview uses sample values and the current unsaved editor configuration.
        Facts refresh instructions only when entering a node.
      </FieldDescription>
      {config.contact_variables.map((k) => (
        <Field key={k}>
          <FieldLabel>{k} (contact sample)</FieldLabel>
          <Input
            aria-label={`Contact sample ${k}`}
            value={contact[k] ?? ""}
            onChange={(e) => {
              setContact({ ...contact, [k]: e.target.value });
              setResult(null);
            }}
          />
        </Field>
      ))}
      {config.fact_slots.map((s) => (
        <Field key={s.key}>
          <FieldLabel>{s.key} (fact sample)</FieldLabel>
          {s.value_type === "boolean" ? (
            <NativeSelect
              aria-label={`Fact sample ${s.key}`}
              value={String(facts[s.key] ?? s.default_value ?? "")}
              onChange={(e) => {
                setFacts({
                  ...facts,
                  [s.key]:
                    e.target.value === "" ? "" : e.target.value === "true",
                });
                setResult(null);
              }}
            >
              <option value="">Unset</option>
              <option value="true">true</option>
              <option value="false">false</option>
            </NativeSelect>
          ) : (
            <Input
              aria-label={`Fact sample ${s.key}`}
              type={s.value_type === "string" ? "text" : "number"}
              value={String(facts[s.key] ?? s.default_value ?? "")}
              onChange={(e) => {
                setFacts({
                  ...facts,
                  [s.key]:
                    e.target.value === "" || s.value_type === "string"
                      ? e.target.value
                      : Number(e.target.value),
                });
                setResult(null);
              }}
            />
          )}
        </Field>
      ))}
      <div className="flex gap-2">
        <Button type="button" disabled={pending} onClick={() => void preview()}>
          Render preview
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={pending}
          onClick={() => void preview(true)}
        >
          Try all empty
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-destructive">
          {error}
        </p>
      )}
      {result && resultSignature === signature && (
        <>
          <FieldLabel>Rendered instructions</FieldLabel>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">
            {JSON.stringify(result.rendered, null, 2)}
          </pre>
          <FieldLabel>Variable resolution</FieldLabel>
          {result.resolution.map((record, index) => (
            <div
              key={`${record.field}:${record.start}:${index}`}
              className="rounded border p-3 text-sm"
            >
              <p className="font-mono text-xs">
                {record.field}: {record.expression}
              </p>
              <p>
                {record.outcome === "all_empty"
                  ? "All candidates empty; renders an empty string."
                  : `${record.selected_key} selected: ${record.value}`}
              </p>
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {record.candidates.map((candidate, candidateIndex) => (
                  <li key={`${candidate.key}:${candidateIndex}`}>
                    {candidate.key}: {JSON.stringify(candidate.value)} —{" "}
                    {candidate.empty_reason === "zero"
                      ? "skipped: numeric zero"
                      : candidate.empty_reason
                        ? "skipped: empty or whitespace"
                        : candidate.key === record.selected_key
                          ? "selected"
                          : "overridden by a later nonempty value"}{" "}
                    ({candidate.source.kind})
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </FieldGroup>
  );
}
