import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import { useAuth } from "@clerk/react";
import { toast } from "sonner";
import { useApi, useSupportSession } from "@/app/api";

export function useResource<T>(path: string, enabled = true) {
  const api = useApi();
  const { orgId } = useAuth();
  const supportSession = useSupportSession();
  const query = useQuery<T, Error>({
    queryKey: ["resource", orgId ?? "no-organization", supportSession ?? "no-support-session", path],
    queryFn: () => api<T>(path),
    enabled,
  });

  useEffect(() => {
    if (query.error) {
      toast.error(query.error.message || "Could not load data");
    }
  }, [query.error]);

  const reload = useCallback(async () => {
    if (enabled) await query.refetch();
  }, [enabled, query.refetch]);

  return {
    data: query.data ?? null,
    loading: enabled && (query.isPending || query.isFetching),
    error: query.error?.message ?? null,
    reload,
  };
}
