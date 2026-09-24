import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";

type Version = {
  id: string;
  version: number;
  status: string;
  config: {
    name?: string;
    system_prompt?: string;
    flow?: {
      prompt_composition?: string;
      nodes?: { id: string; prompt: string }[];
    };
    llm?: { provider?: string; model?: string };
  };
};

export function AgentVersionPage() {
  const { agentId, versionId } = useParams();
  const api = useApi();
  const [version, setVersion] = useState<Version | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!agentId) return;
    api<{ versions: Version[] }>("/agents/" + agentId + "/versions")
      .then((data) =>
        setVersion(data.versions.find((item) => item.id === versionId) ?? null),
      )
      .catch((cause) => {
        const message =
          cause instanceof Error ? cause.message : "Could not load version";
        setError(message);
        toast.error(message);
      })
      .finally(() => setLoading(false));
  }, [api, agentId, versionId]);
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 lg:p-6">
      <Button asChild variant="link" className="self-start">
        <Link to="/runs">Back to runs</Link>
      </Button>
      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : version ? (
        <Card>
          <CardHeader>
            <CardTitle>
              {version.config.name ?? "Agent"} · v{version.version}
            </CardTitle>
            <CardDescription>
              Read-only version reference. Full editor is a later page slice.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Badge variant="secondary">{version.status}</Badge>
            <p className="text-sm">
              LLM: {version.config.llm?.provider ?? "Unknown"} /{" "}
              {version.config.llm?.model ?? "Unknown"}
            </p>
            <p className="text-sm">
              Prompt composition:{" "}
              {version.config.flow?.prompt_composition ?? "Unknown"}
            </p>
            <section>
              <h2 className="mb-1 text-sm font-medium">System prompt</h2>
              <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                {version.config.system_prompt ?? "Not set"}
              </pre>
            </section>
            {version.config.flow?.nodes?.map((node) => (
              <section key={node.id}>
                <h2 className="mb-1 text-sm font-medium">Node · {node.id}</h2>
                <pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-xs">
                  {node.prompt}
                </pre>
              </section>
            ))}
          </CardContent>
        </Card>
      ) : (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Version unavailable</EmptyTitle>
            <EmptyDescription>
              {error || "Version not found for this agent."}
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
    </div>
  );
}
