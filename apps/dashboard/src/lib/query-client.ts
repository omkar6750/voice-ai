import { dehydrate, hydrate, QueryClient } from "@tanstack/react-query";

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

const CACHE_VERSION = "dashboard-query-cache-v2";
const MAX_BYTES = 1024 * 1024;
const MAX_AGE = 30 * 60_000;
const catalogs = new Set([
  "/providers",
  "/tools",
  "/contacts/variables",
  "/agents",
]);
const cacheKey = (userId: string) => `${CACHE_VERSION}:${userId}`;

export function isSafeQuery(query: { queryKey: readonly unknown[] }): boolean {
  const [scope, userOrOrg, supportSession, path] = query.queryKey;
  if (scope === "resource") {
    return (
      Boolean(userOrOrg && query.queryKey[4]) &&
      supportSession === "no-support-session" &&
      typeof path === "string" &&
      catalogs.has(path)
    );
  }
  if (scope === "runs")
    return (
      Boolean(userOrOrg && query.queryKey[2]) && query.queryKey[3] === null
    );
  return false;
}

export function restoreQueryCache(userId: string): void {
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const key = sessionStorage.key(i);
      if (
        key?.startsWith("dashboard-query-cache-") &&
        !key.startsWith(CACHE_VERSION + ":")
      )
        sessionStorage.removeItem(key);
    }
    const raw = sessionStorage.getItem(cacheKey(userId));
    if (!raw) return;
    if (new TextEncoder().encode(raw).byteLength > MAX_BYTES)
      throw new Error("Cache too large");
    const envelope = JSON.parse(raw);
    if (
      envelope.version !== CACHE_VERSION ||
      Date.now() - envelope.savedAt > MAX_AGE ||
      envelope.savedAt > Date.now()
    )
      throw new Error("Cache expired");
    const state = envelope.state as Parameters<typeof hydrate>[1];
    state.queries = (state.queries ?? []).filter(
      (query) =>
        isSafeQuery(query) &&
        (query.queryKey[0] === "resource"
          ? query.queryKey[4] === userId
          : query.queryKey[1] === userId) &&
        query.state.status === "success" &&
        Date.now() - query.state.dataUpdatedAt <= MAX_AGE,
    );
    hydrate(queryClient, state);
  } catch {
    sessionStorage.removeItem(cacheKey(userId));
  }
}

export function persistQueryCache(userId: string): () => void {
  let debounce: ReturnType<typeof setTimeout> | undefined;
  let idle: number | undefined;
  let fallback: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  const persist = () => {
    if (disposed) return;
    idle = undefined;
    fallback = undefined;
    try {
      const state = dehydrate(queryClient, {
        shouldDehydrateQuery: (query) =>
          isSafeQuery(query) &&
          (query.queryKey[0] === "resource"
            ? query.queryKey[4] === userId
            : query.queryKey[1] === userId) &&
          query.state.status === "success" &&
          Date.now() - query.state.dataUpdatedAt <= MAX_AGE,
      });
      state.mutations = [];
      let raw = "";
      while (true) {
        raw = JSON.stringify({
          version: CACHE_VERSION,
          savedAt: Date.now(),
          state,
        });
        if (new TextEncoder().encode(raw).byteLength <= MAX_BYTES) break;
        if (!state.queries.length) return;
        state.queries.sort(
          (a, b) => b.state.dataUpdatedAt - a.state.dataUpdatedAt,
        );
        state.queries.pop();
      }
      sessionStorage.setItem(cacheKey(userId), raw);
    } catch {
      /* An unavailable cache must not prevent rendering. */
    }
  };
  const cancel = () => {
    clearTimeout(debounce);
    clearTimeout(fallback);
    if (idle !== undefined) window.cancelIdleCallback(idle);
  };
  const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
    if (
      event.type !== "updated" ||
      event.action.type !== "success" ||
      !isSafeQuery(event.query)
    )
      return;
    cancel();
    debounce = setTimeout(() => {
      if ("requestIdleCallback" in window)
        idle = window.requestIdleCallback(persist, { timeout: 2000 });
      else fallback = setTimeout(persist, 0);
    }, 1000);
  });
  return () => {
    disposed = true;
    cancel();
    unsubscribe();
  };
}

export function clearQueryCache(): void {
  queryClient.clear();
  for (let i = sessionStorage.length - 1; i >= 0; i--) {
    const key = sessionStorage.key(i);
    if (key?.startsWith("dashboard-query-cache-"))
      sessionStorage.removeItem(key);
  }
}
