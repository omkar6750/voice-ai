import { Link, useParams, useSearchParams } from "react-router-dom";
import { useOrganizationAccess } from "@/app/access";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { useResource } from "@/lib/resources";
import { ChunksPanel } from "./ChunksPanel";
import { IngestionPanel } from "./IngestionPanel";
import { SearchPanel } from "./SearchPanel";
import { SourcesPanel } from "./SourcesPanel";
import type { KnowledgeBase } from "./types";

const sections = ["Sources", "Chunks", "Search", "Ingestion"] as const;
export function KnowledgeDetailPage() {
  const { baseId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const { canManage } = useOrganizationAccess();
  const { data, loading, error, reload } = useResource<{
    knowledge_bases: KnowledgeBase[];
  }>("/knowledge-bases");
  const base = data?.knowledge_bases.find((item) => item.id === baseId);
  const requestedSection =
    sections.find((item) => item.toLowerCase() === params.get("section")) ??
    "Sources";
  const section = requestedSection === "Search" && !canManage ? "Sources" : requestedSection;
  return (
    <PageBody>
      <PageHeader
        title={base?.name ?? "Knowledge base"}
        description="Current mutable corpus and ingestion settings."
        action={
          <Button asChild variant="outline">
            <Link to="/knowledge">All bases</Link>
          </Button>
        }
        readOnlyAction={
          <Button asChild variant="outline">
            <Link to="/knowledge">All bases</Link>
          </Button>
        }
      />
      <LoadState
        loading={loading}
        error={error}
        empty={!base ? "Knowledge base not found." : undefined}
      >
        {base && (
          <>
            <nav
              aria-label="Knowledge sections"
              className="flex gap-1 border-b pb-2"
            >
              {sections.filter((item) => item !== "Search" || canManage).map((item) => (
                <Button
                  type="button"
                  key={item}
                  size="sm"
                  variant={section === item ? "secondary" : "ghost"}
                  onClick={() => setParams({ section: item.toLowerCase() })}
                >
                  {item}
                </Button>
              ))}
            </nav>
            {section === "Sources" && <SourcesPanel baseId={baseId} />}
            {section === "Chunks" && <ChunksPanel baseId={baseId} />}
            {section === "Ingestion" && (
              <IngestionPanel
                key={JSON.stringify(base.config)}
                base={base}
                saved={reload}
              />
            )}
            {section === "Search" && canManage && <SearchPanel baseId={baseId} />}
          </>
        )}
      </LoadState>
    </PageBody>
  );
}
