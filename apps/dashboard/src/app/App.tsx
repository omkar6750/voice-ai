import { SignIn, SignUp, useAuth, UserButton } from "@clerk/react";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ApiContext, SupportSessionContext, request } from "./api";
import { AppShell } from "./AppShell";
import { OrgExplorer } from "./OrgExplorer";
import { CreateOrganizationPage } from "@/pages/organizations/create";
import { PlatformOrganizationsPage } from "@/pages/organizations/platform";
import type { OrganizationView } from "./organizations";
import type { AccountView } from "./organizations";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

const OrganizationArea = lazy(() =>
  import("@/pages/organizations/area").then((page) => ({ default: page.OrganizationArea })),
);

export function App() {
  const { getToken, isLoaded, isSignedIn, userId, orgId } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [organizations, setOrganizations] = useState<OrganizationView[]>([]);
  const [account, setAccount] = useState<AccountView | null>(null);
  const [orgsStatus, setOrgsStatus] = useState<"loading" | "ready" | "error">("loading");
  const [orgsError, setOrgsError] = useState<string | null>(null);
  const [accessStatus, setAccessStatus] = useState<"checking" | "allowed" | "denied">("checking");
  const [supportToken, setSupportToken] = useState<string | null>(null);
  const [supportOrganization, setSupportOrganization] = useState<{ id: string; name: string } | null>(null);
  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;
    setOrgsStatus("loading");
    const loadOrganizations = async () => {
      try {
        const token = await getToken();
        if (!token) throw new Error("No Clerk session token");
        const joined = await request<OrganizationView[]>(token, "/orgs");
        const accountView = await request<AccountView>(token, "/me");
        if (!cancelled) {
          setOrganizations(joined);
          setAccount(accountView);
          setOrgsError(null);
          setOrgsStatus("ready");
        }
      } catch (cause) {
        if (!cancelled) {
          setOrgsError(cause instanceof Error ? cause.message : "Could not load organizations");
          setOrgsStatus("error");
        }
      }
    };
    void loadOrganizations();
    window.addEventListener("focus", loadOrganizations);
    return () => { cancelled = true; window.removeEventListener("focus", loadOrganizations); };
  }, [getToken, isSignedIn, userId, orgId]);
  useEffect(() => {
    if (!isSignedIn || !orgId || orgsStatus !== "ready" || !organizations.some((org) => org.id === orgId && org.registered)) {
      setAccessStatus("denied");
      return;
    }
    let cancelled = false;
    setAccessStatus("checking");
    void (async () => {
      try {
        const sessionToken = await getToken();
        if (!sessionToken) throw new Error("No Clerk session token");
        await request(sessionToken, "/auth/organization-access");
        if (!cancelled) setAccessStatus("allowed");
      } catch {
        if (!cancelled) setAccessStatus("denied");
      }
    })();
    return () => { cancelled = true; };
  }, [getToken, isSignedIn, orgId, orgsStatus, organizations]);
  const api = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      const sessionToken = await getToken();
      if (!sessionToken) throw new Error("Sign in required");
      const method = (init?.method ?? "GET").toUpperCase();
      if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS" && !supportToken) {
        const activeRole = organizations.find((organization) => organization.id === orgId)?.role;
        const isBrowserTestLifecycle = path === "/browser-sessions" || path.startsWith("/browser-sessions/");
        if (activeRole !== "org:admin" && !isBrowserTestLifecycle) {
          throw new Error("Organization admin access is required for this action");
        }
      }
      return request<T>(sessionToken, path, init, supportToken);
    },
    [getToken, supportToken, organizations, orgId],
  );
  const enterSupport = useCallback(async (id: string, name: string) => {
    const sessionToken = await getToken();
    if (!sessionToken) throw new Error("Sign in required");
    const result = await request<{ token: string }>(
      sessionToken,
      `/platform/orgs/${id}/support-session`,
      { method: "POST" },
    );
    setSupportToken(result.token);
    setSupportOrganization({ id, name });
    navigate("/platform/support");
  }, [getToken, navigate]);
  const exitSupport = useCallback(async () => {
    const sessionToken = await getToken();
    if (sessionToken && supportToken) {
      await request(sessionToken, "/platform/support-session", { method: "DELETE" }, supportToken);
    }
    setSupportToken(null);
    setSupportOrganization(null);
    navigate("/platform/orgs");
  }, [getToken, navigate, supportToken]);
  if (!isLoaded) return <main className="grid min-h-svh place-items-center">Loading…</main>;
  if (!isSignedIn) {
    return (
      <Routes>
        <Route path="/sign-in/*" element={<main className="grid min-h-svh place-items-center px-4"><SignIn routing="path" path="/sign-in" /></main>} />
        <Route path="/sign-up/*" element={<main className="grid min-h-svh place-items-center px-4"><SignUp routing="path" path="/sign-up" /></main>} />
        <Route path="*" element={
          <main className="mx-auto flex min-h-svh max-w-3xl flex-col justify-center gap-6 px-6">
            <p className="text-sm font-medium text-muted-foreground">Voice AI</p>
            <h1 className="text-4xl font-semibold tracking-tight">Build and test voice agents with your team.</h1>
            <p className="max-w-xl text-muted-foreground">Sign in with your email, create or join an organization, invite teammates, and securely manage voice agents together.</p>
            <div className="flex gap-3">
              <Button asChild><Link to="/sign-up">Sign up</Link></Button>
              <Button variant="outline" asChild><Link to="/sign-in">Log in</Link></Button>
            </div>
          </main>
        } />
      </Routes>
    );
  }
  if (pathname.startsWith("/sign-")) return <Navigate to="/" replace />;
  return (
    <TooltipProvider>
      <ApiContext.Provider value={api}>
        <SupportSessionContext.Provider value={supportToken}>
        {pathname.startsWith("/platform/support") && supportToken && supportOrganization && account?.platform_admin
          ? <AppShell organizations={organizations} platformAdmin supportOrganization={supportOrganization} onExitSupport={() => void exitSupport()} />
          : pathname === "/platform/orgs" && account?.platform_admin
          ? <PlatformOrganizationsPage onEnterSupport={enterSupport} />
          : accessStatus === "denied" && /^\/orgs\/[^/]+(?:\/members|\/settings)?$/.test(pathname)
          ? <Suspense fallback={<main className="p-6" role="status">Loading organization…</main>}>
              <Routes>
                <Route path="/orgs/:orgId" element={<OrganizationArea />} />
                <Route path="/orgs/:orgId/members" element={<OrganizationArea />} />
                <Route path="/orgs/:orgId/settings" element={<OrganizationArea />} />
              </Routes>
            </Suspense>
          : pathname === "/orgs" || pathname.startsWith("/onboarding/") || !orgId || !organizations.some((org) => org.id === orgId && org.registered) || accessStatus === "denied"
          ? <Routes>
              <Route path="/onboarding/create-org" element={<CreateOrganizationPage account={account} />} />
              <Route path="*" element={<OrgExplorer organizations={organizations} loading={orgsStatus === "loading"} error={orgsError} canCreate={Boolean(account?.can_create_org && account.organization_creation_enabled)} availableOrgIds={account?.organizations.filter((org) => org.capabilities.includes("browser_test")).map((org) => org.id) ?? []} platformAdmin={account?.platform_admin ?? false} />} />
            </Routes>
          : accessStatus === "allowed"
            ? <AppShell organizations={organizations} platformAdmin={account?.platform_admin ?? false} />
            : <main className="grid min-h-svh place-items-center px-4"><div className="flex items-center gap-3"><UserButton /><p role="status">Checking organization access…</p></div></main>}
        </SupportSessionContext.Provider>
      </ApiContext.Provider>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  );
}
