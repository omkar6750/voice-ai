import { Link } from "react-router-dom";
import { LoadState, PageBody, PageHeader } from "@/components/record-page";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useResource } from "@/lib/resources";

type Tool = { id: string; name: string };
export function ToolsPage() {
  const { data, loading, error } = useResource<{ tools: Tool[] }>("/tools");
  return (
    <PageBody>
      <PageHeader
        title="Tools"
        description="Published tool versions can be pinned to agent drafts. Node access is configured in each flow."
      />
      <LoadState
        loading={loading}
        error={error}
        empty={
          data?.tools.length === 0 ? "No tools registered yet." : undefined
        }
      >
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tool</TableHead>
              <TableHead className="text-right">Versions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data?.tools.map((tool) => (
              <TableRow key={tool.id}>
                <TableCell className="font-medium">{tool.name}</TableCell>
                <TableCell className="text-right">
                  <Button asChild variant="link">
                    <Link to={`/tools/${tool.id}`}>View versions</Link>
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </LoadState>
      <p className="text-xs text-muted-foreground">
        New registered handlers need a backend handler catalog. HTTP tool
        authoring needs destination allowlist feedback. Both are deferred, not
        represented as working controls.
      </p>
    </PageBody>
  );
}
