import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@clerk/react";
import { useApi } from "@/app/api";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { SearchableSelect } from "@/components/ui/searchable-select";
import type { OptionItem } from "@/lib/geo-data";
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
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freeOnly, setFreeOnly] = useState(false);

  useEffect(() => {
    if (!orgId || !credentialId) {
      setCatalog(null);
      return;
    }
    let cancelled = false;
    setCatalog(null);
    setError(null);
    void (async () => {
      try {
        const page = await api<Catalog>(
          `/orgs/${orgId}/openrouter/${credentialId}/models?limit=1000`,
        );
        if (!cancelled) {
          setCatalog(page);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled)
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not load OpenRouter models",
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, credentialId, orgId]);

  const items = useMemo(
    () =>
      (catalog?.items ?? []).filter(
        (item) =>
          item.runtime_supported &&
          item.slots.includes("llm") &&
          (!freeOnly || item.is_free),
      ),
    [catalog, freeOnly],
  );
  const options = useMemo<OptionItem[]>(
    () =>
      items.map((item) => {
        const prompt = Number(item.pricing.prompt) * 1_000_000;
        const completion = Number(item.pricing.completion) * 1_000_000;
        return {
          value: item.id,
          label: item.name,
          badge: item.is_free ? "Free" : undefined,
          sublabel: item.is_free
            ? item.id
            : `$${prompt.toPrecision(3)} input / $${completion.toPrecision(3)} output per 1M`,
          keywords: [item.id, item.author ?? ""],
        };
      }),
    [items],
  );
  return (
    <Field>
      <FieldLabel htmlFor={`openrouter-${stage}-model`}>
        OpenRouter model
      </FieldLabel>
      <div className="flex items-center gap-2">
        <SearchableSelect
          id={`openrouter-${stage}-model`}
          value={value}
          onChange={onChange}
          options={options}
          selectionOnly
          disabled={disabled || !credentialId || !catalog}
          placeholder="Search models..."
          emptyText="No models match this search or filter."
          className="flex-1"
        />
        <button
          type="button"
          disabled={disabled || !catalog}
          aria-pressed={freeOnly}
          onClick={() => setFreeOnly((current) => !current)}
          className={`h-9 rounded-md border px-3 text-xs ${freeOnly ? "border-primary bg-primary/10 text-primary" : "border-input text-muted-foreground"}`}
        >
          Free only
        </button>
      </div>
      <FieldDescription>
        {error ??
          (catalog
            ? `${items.length} ${freeOnly ? "free " : ""}usable models · ${stage}${catalog.stale ? " · cached catalog" : ""}`
            : "Bind an OpenRouter credential to load its account-accessible models.")}
      </FieldDescription>
    </Field>
  );
}
