import { useAuth } from "@clerk/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";
import { toast } from "sonner";
import { useApi, useSupportSession } from "@/app/api";
import { Button } from "@/components/ui/button";

export function useToolResource<T>(path: string, enabled = true) {
  const api = useApi();
  const client = useQueryClient();
  const { userId, orgId } = useAuth();
  const support = useSupportSession();
  const scope = ["tools-workspace", userId, orgId, support];
  const key = [...scope, path];
  const query = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => api<T>(path, { signal }),
    enabled,
    staleTime: 30_000,
  });
  return {
    ...query,
    setData: (data: T) => client.setQueryData(key, data),
    invalidate: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: scope }),
        // Existing agent binding pickers use the legacy full-version resource.
        client.invalidateQueries({
          predicate: (query) => {
            const [kind, organization, session, resourcePath] = query.queryKey;
            return (
              kind === "resource" &&
              organization === (orgId ?? "no-organization") &&
              session === (support ?? "no-support-session") &&
              typeof resourcePath === "string" &&
              (resourcePath === "/tools" ||
                resourcePath.startsWith("/tools/") ||
                resourcePath.startsWith("/tool-versions/"))
            );
          },
        }),
      ]),
  };
}

export function CopyId({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1 text-xs text-muted-foreground">
      <span>{label}</span>
      <code className="truncate" title={value}>
        {value}
      </code>
      <Button
        variant="ghost"
        size="icon-xs"
        aria-label={`Copy ${label}`}
        onClick={() => {
          void navigator.clipboard.writeText(value).then(
            () => toast.success(`${label} copied`),
            () => toast.error("Could not copy ID"),
          );
        }}
      >
        <Copy />
      </Button>
    </span>
  );
}
