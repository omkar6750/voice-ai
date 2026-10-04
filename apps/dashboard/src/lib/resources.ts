import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect } from "react";
import { useAuth } from "@clerk/react";
import { toast } from "sonner";
import { useApi, useSupportSession } from "@/app/api";

export function useResource<T>(path: string, enabled = true) {
  const api = useApi();
  const { orgId, userId } = useAuth();
  const supportSession = useSupportSession();
  const query = useQuery<T, Error>({
    queryKey: ["resource", orgId ?? "no-organization", supportSession ?? "no-support-session", path, userId],
    queryFn: ({ signal }) => api<T>(path, { signal }),
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
      // Keep cached data visible while a stale query refreshes in the
      // background. Full-page loading is only appropriate before first data.
      loading: enabled && query.isPending,
      fetching: enabled && query.isFetching,
      error: query.error?.message ?? null,
      reload,
    };
}
