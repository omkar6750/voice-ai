import { useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { useApi } from "@/app/api";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { components } from "@/generated/api";

type Catalog = components["schemas"]["ModelCatalogResponse"];

export function OpenRouterModelPicker({
  stage,
  credentialId,
  value,
  disabled,
  onChange,
}: {
  stage: string;
  credentialId?: string;
  value: string;
  disabled: boolean;
  onChange: (model: string) => void;
}) {
  const api = useApi();
  const { orgId } = useAuth();
  const [query, setQuery] = useState("");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!orgId || !credentialId) {
      setCatalog(null);
      return;
    }
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams({ limit: "100", q: query });
      void api<Catalog>(`/orgs/${orgId}/openrouter/${credentialId}/models?${params}`)
        .then((result) => { setCatalog(result); setError(null); })
        .catch((cause) => setError(cause instanceof Error ? cause.message : "Could not load OpenRouter models"));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [api, credentialId, orgId, query]);

  const items = catalog?.items ?? [];
  return <Field>
    <FieldLabel htmlFor={`openrouter-${stage}-search`}>OpenRouter model</FieldLabel>
    <Input
      id={`openrouter-${stage}-search`}
      value={query}
      placeholder="Search model name or slug"
      disabled={disabled || !credentialId}
      onChange={(event) => setQuery(event.target.value)}
    />
    <NativeSelect
      id={`openrouter-${stage}-model`}
      className="w-full"
      value={value}
      disabled={disabled || !credentialId || items.length === 0}
      onChange={(event) => onChange(event.target.value)}
    >
      {!items.some((item) => item.id === value) && value && <option value={value}>{value} (stored)</option>}
      {items.map((item) => <option key={item.id} value={item.id}>
        {item.name} · {item.is_free ? "Free" : `$${Number(item.pricing.prompt) * 1_000_000}/M prompt`}
      </option>)}
    </NativeSelect>
    <FieldDescription>
      {error ?? (catalog ? `${catalog.total_count ?? items.length} account-accessible models · ${stage}` : "Bind an OpenRouter credential to load account-accessible models.")}
    </FieldDescription>
  </Field>;
}
