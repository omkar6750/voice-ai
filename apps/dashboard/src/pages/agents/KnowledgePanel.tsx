import { LoadState, ReadOnlyValue } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/ui/field";
import { useResource } from "@/lib/resources";
import { NumberField } from "./ConfigFields";
import type { AgentConfig } from "./types";

type Base = { id: string; name: string };

export function KnowledgePanel({
  config,
  change,
  disabled,
}: {
  config: AgentConfig;
  change: (next: AgentConfig) => void;
  disabled: boolean;
}) {
  const { data, loading, error } = useResource<{ knowledge_bases: Base[] }>(
    "/knowledge-bases",
  );
  function updateRetrieval(next: Partial<AgentConfig["retrieval"]>) {
    change({ ...config, retrieval: { ...config.retrieval, ...next } });
  }
  return (
    <div className="grid max-w-5xl gap-8 lg:grid-cols-2">
      <section className="flex flex-col gap-3">
        <h2 className="text-base font-semibold">Knowledge bases</h2>
        <LoadState
          loading={loading}
          error={error}
          empty={
            data?.knowledge_bases.length === 0
              ? "No knowledge bases yet."
              : undefined
          }
        >
          <div className="flex flex-wrap gap-2">
            {data?.knowledge_bases.map((base) => {
              const selected = config.knowledge_base_ids.includes(base.id);
              return (
                <Button
                  key={base.id}
                  type="button"
                  size="sm"
                  variant={selected ? "secondary" : "outline"}
                  aria-pressed={selected}
                  disabled={disabled}
                  onClick={() =>
                    change({
                      ...config,
                      knowledge_base_ids: selected
                        ? config.knowledge_base_ids.filter(
                            (id) => id !== base.id,
                          )
                        : [...config.knowledge_base_ids, base.id],
                    })
                  }
                >
                  {base.name}
                </Button>
              );
            })}
          </div>
        </LoadState>
        <p className="text-xs text-muted-foreground">
          KB contents are mutable. Runs retain exact retrieval evidence, not
          corpus versions.
        </p>
      </section>
      <section className="flex flex-col gap-4">
        <h2 className="text-base font-semibold">Retrieval</h2>
        <FieldGroup>
          <NumberField
            id="top-k"
            label="Top results"
            value={config.retrieval.top_k}
            min={1}
            max={100}
            disabled={disabled}
            onChange={(top_k) => updateRetrieval({ top_k })}
          />
          <NumberField
            id="keyword-weight"
            label="Keyword weight"
            value={config.retrieval.keyword_weight}
            min={0}
            max={1}
            step={0.05}
            disabled={disabled}
            onChange={(keyword_weight) => updateRetrieval({ keyword_weight })}
          />
          <NumberField
            id="vector-weight"
            label="Vector weight"
            value={config.retrieval.vector_weight}
            min={0}
            max={1}
            step={0.05}
            disabled={disabled}
            onChange={(vector_weight) => updateRetrieval({ vector_weight })}
          />
          <NumberField
            id="rrf-k"
            label="Fusion RRF k"
            value={config.retrieval.rrf_k}
            min={1}
            disabled={disabled}
            onChange={(rrf_k) => updateRetrieval({ rrf_k })}
          />
          <NumberField
            id="result-budget"
            label="Result token budget"
            value={config.retrieval.result_budget_tokens}
            min={1}
            disabled={disabled}
            onChange={(result_budget_tokens) =>
              updateRetrieval({ result_budget_tokens })
            }
          />
          <NumberField
            id="retrieval-timeout"
            label="Search timeout, seconds"
            value={config.retrieval.timeout_secs}
            min={0.1}
            step={0.5}
            disabled={disabled}
            onChange={(timeout_secs) => updateRetrieval({ timeout_secs })}
          />
        </FieldGroup>
        <ReadOnlyValue
          label="Minimum vector similarity"
          value={config.retrieval.min_vector_similarity ?? "Not set"}
        />
        <ReadOnlyValue
          label="Minimum keyword score"
          value={config.retrieval.min_keyword_score ?? "Not set"}
        />
        <ReadOnlyValue
          label="Reranking"
          value={String(config.retrieval.reranking_enabled)}
          reason="Current backend contract only supports disabled."
        />
      </section>
    </div>
  );
}
