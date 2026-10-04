import { useAuth } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";
import { useApi } from "./api";

export type AppContext = {
  user_id: string;
  active_org_id: string | null;
  active_org_name: string | null;
  active_org_registered: boolean;
  active_org_role: "org:admin" | "org:member" | null;
  is_owner: boolean;
  platform_admin: boolean;
  user_disabled: boolean;
  can_create_org: boolean;
  organization_creation_enabled: boolean;
  capabilities: string[];
};

/**
 * Product-local context is deliberately separate from Clerk state. Clerk is
 * the source of truth for sign-in, active organization, and live membership.
 * This query supplies the API's effective role and local ownership.
 */
export function useAppContext(enabled = true) {
  const api = useApi();
  const { isLoaded, isSignedIn, userId, orgId, orgRole } = useAuth();
  return useQuery<AppContext, Error>({
    queryKey: ["app-context", userId ?? "anonymous", orgId ?? "personal", orgRole ?? "none"],
    queryFn: () => api<AppContext>("/auth/context"),
    enabled: Boolean(enabled && isLoaded && isSignedIn && userId),
    staleTime: 2 * 60_000,
    gcTime: 30 * 60_000,
    refetchOnWindowFocus: false,
  });
}
