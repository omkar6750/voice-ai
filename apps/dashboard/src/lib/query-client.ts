import { dehydrate, hydrate, QueryClient } from "@tanstack/react-query";

// Keep server-state policy in one place. Individual resources can opt into
// different behavior later without adding a second fetching abstraction.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 30 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const CACHE_VERSION = "dashboard-query-cache-v1";

function cacheKey(userId: string): string {
  return `${CACHE_VERSION}:${userId}`;
}

function isSafeQuery(query: { queryKey: readonly unknown[] }): boolean {
  const [scope, userOrOrg, supportSession] = query.queryKey;
  // Never persist support-session data or anything that is not scoped to the
  // current authenticated user/org. Clerk tokens are never part of query data.
  if (scope === "account") return Boolean(userOrOrg);
  const path = typeof query.queryKey[3] === "string" ? query.queryKey[3] : "";
  const containsSensitiveData = /credentials|secrets/i.test(path);
  return scope === "resource" && supportSession === "no-support-session" && Boolean(userOrOrg) && !containsSensitiveData;
}

export function restoreQueryCache(userId: string): void {
  try {
    const raw = sessionStorage.getItem(cacheKey(userId));
    if (!raw) return;
    const parsed = JSON.parse(raw) as Parameters<typeof hydrate>[1];
    hydrate(queryClient, parsed);
  } catch {
    sessionStorage.removeItem(cacheKey(userId));
  }
}

export function persistQueryCache(userId: string): () => void {
  const persist = () => {
    try {
      const dehydrated = dehydrate(queryClient, {
        shouldDehydrateQuery: isSafeQuery,
      });
      sessionStorage.setItem(cacheKey(userId), JSON.stringify(dehydrated));
    } catch {
      // Storage can be unavailable or full. The in-memory cache still works.
    }
  };
  persist();
  return queryClient.getQueryCache().subscribe(persist);
}

export function clearQueryCache(): void {
  queryClient.clear();
  for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
    const key = sessionStorage.key(index);
    if (key?.startsWith(`${CACHE_VERSION}:`)) sessionStorage.removeItem(key);
  }
}
