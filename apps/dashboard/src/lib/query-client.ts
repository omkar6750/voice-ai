import { QueryClient } from "@tanstack/react-query";

// Keep server-state policy in one place. Individual resources can opt into
// different behavior later without adding a second fetching abstraction.
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      gcTime: 5 * 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
