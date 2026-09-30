import { SignIn, SignUp, useAuth, useOrganization } from "@clerk/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { ApiContext, ApiError, SupportSessionContext, request, useApi } from "./api";
import { useAppContext } from "./app-context";
import { PlatformKeepAwake } from "./PlatformKeepAwake";
import { clerkUrls } from "./clerk-config";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { clearQueryCache, persistQueryCache, restoreQueryCache } from "@/lib/query-client";

const AppShell = lazy(() => import("./AppShell").then((page) => ({ default: page.AppShell })));
const PlatformOrganizationsPage = lazy(() => import("@/pages/organizations/platform").then((page) => ({ default: page.PlatformOrganizationsPage })));
const OrganizationListPage = lazy(() => import("@/pages/organizations/clerk").then((page) => ({ default: page.OrganizationListPage })));
const OrganizationCreatePage = lazy(() => import("@/pages/organizations/clerk").then((page) => ({ default: page.OrganizationCreatePage })));
const OrganizationProfilePage = lazy(() => import("@/pages/organizations/clerk").then((page) => ({ default: page.OrganizationProfilePage })));

function LoadingPage({ children = "Loading dashboard…" }: { children?: string }) {
  return <main className="grid min-h-svh place-items-center" role="status">{children}</main>;
}

async function requestWithFreshToken<T>(
  getToken: ReturnType<typeof useAuth>["getToken"],
  path: string,
  init?: RequestInit,
  supportSession?: string | null,
): Promise<T> {
  const token = await getToken();
  if (!token) throw new Error("Sign in required");
  try {
    return await request<T>(token, path, init, supportSession);
  } catch (cause) {
    if (!(cause instanceof ApiError) || cause.status !== 401) throw cause;
    const freshToken = await getToken({ skipCache: true });
    if (!freshToken || freshToken === token) throw cause;
    return request<T>(freshToken, path, init, supportSession);
  }
}

function SignedOutRoutes() {
  return <Routes>
    <Route path="/sign-in/*" element={<main className="grid min-h-svh place-items-center px-4"><SignIn routing="path" path={clerkUrls.signIn} forceRedirectUrl={clerkUrls.afterSignIn} /></main>} />
    <Route path="/sign-up/*" element={<main className="grid min-h-svh place-items-center px-4"><SignUp routing="path" path={clerkUrls.signUp} forceRedirectUrl={clerkUrls.afterSignUp} /></main>} />
    <Route path="*" element={<main className="mx-auto flex min-h-svh max-w-3xl flex-col justify-center gap-6 px-6"><p className="text-sm font-medium text-muted-foreground">Voice AI</p><h1 className="text-4xl font-semibold tracking-tight">Build and test voice agents with your team.</h1><p className="max-w-xl text-muted-foreground">Sign in with your email, create or join an organization, invite teammates, and securely manage voice agents together.</p><div className="flex gap-3"><Button asChild><Link to="/sign-up">Sign up</Link></Button><Button variant="outline" asChild><Link to="/sign-in">Log in</Link></Button></div></main>} />
  </Routes>;
}

function ProvisionOrganization() {
  const { orgId, orgRole } = useAuth();
  const { organization } = useOrganization();
  const api = useApi();
  const queryClient = useQueryClient();
  const provision = useMutation({
    mutationFn: () => api(`/orgs/${orgId}/provision`, { method: "POST", body: JSON.stringify({ name: organization?.name }) }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["app-context"] }),
  });
  const { mutate, isPending, isSuccess, isError, error } = provision;
  useEffect(() => {
    if (orgId && (orgRole === "org:owner" || orgRole === "org:admin") && organization?.name && !isPending && !isSuccess) mutate();
  }, [isPending, isSuccess, mutate, orgId, orgRole, organization?.name]);
  if (isError) return <main className="mx-auto max-w-xl p-8"><p role="alert" className="text-destructive">Organization setup failed. {error.message}</p></main>;
  return <LoadingPage>Setting up organization…</LoadingPage>;
}

function AuthenticatedApp() {
  const { isLoaded, isSignedIn, userId, orgId, orgRole, getToken } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const platformRoute = pathname.startsWith("/platform");
  // An organization-scoped context query is product state, not an auth
  // check. It may warm the cache in the background, but normal pages render
  // from Clerk immediately instead of waiting for this request.
  const appContext = useAppContext(platformRoute || Boolean(orgId));
  const [supportToken, setSupportToken] = useState<string | null>(null);
  const [supportOrganization, setSupportOrganization] = useState<{ id: string; name: string } | null>(null);
  const supportTokenRef = useRef(supportToken);
  supportTokenRef.current = supportToken;

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId) return;
    restoreQueryCache(userId);
    return persistQueryCache(userId);
  }, [isLoaded, isSignedIn, userId]);
  useEffect(() => {
    if (!isSignedIn) {
      clearQueryCache();
      setSupportToken(null);
      setSupportOrganization(null);
    }
  }, [isSignedIn]);
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: ["app-context"] });
    void queryClient.cancelQueries({ predicate: (query) => query.queryKey[0] === "resource" });
  }, [orgId, orgRole, queryClient]);

  const api = useCallback(async <T,>(path: string, init?: RequestInit) => {
    return requestWithFreshToken<T>(getToken, path, init, supportTokenRef.current);
  }, [getToken]);
  const enterSupport = useCallback(async (id: string, name: string) => {
    const token = await getToken();
    if (!token) throw new Error("Sign in required");
    const result = await request<{ token: string }>(token, `/platform/orgs/${id}/support-session`, { method: "POST" });
    setSupportToken(result.token);
    setSupportOrganization({ id, name });
    navigate("/platform/support");
  }, [getToken, navigate]);
  const exitSupport = useCallback(async () => {
    const token = await getToken();
    if (token && supportToken) await request(token, "/platform/support-session", { method: "DELETE" }, supportToken);
    setSupportToken(null);
    setSupportOrganization(null);
    navigate("/platform/orgs");
  }, [getToken, navigate, supportToken]);

  if (!isLoaded) return <LoadingPage>Loading…</LoadingPage>;
  if (!isSignedIn) return <SignedOutRoutes />;
  if (pathname.startsWith("/sign-")) return <Navigate to="/runs" replace />;

  const platformAdmin = Boolean(appContext.data?.platform_admin);
  const contextResolved = appContext.isSuccess && !appContext.isFetching;
  const registered = appContext.data?.active_org_registered === true;

  // Platform access is local product authorization and must still be
  // confirmed by the backend context endpoint. Only platform routes wait for
  // that answer; the regular dashboard never does.
  if (platformRoute && appContext.isPending) {
    return <LoadingPage>Checking platform access…</LoadingPage>;
  }
  if (platformRoute && (appContext.isError || !platformAdmin)) {
    return <Navigate to="/runs" replace />;
  }

  return <TooltipProvider>
    <ApiContext.Provider value={api}>
      <PlatformKeepAwake enabled={platformAdmin} showControls={pathname === "/platform/orgs" && platformAdmin} />
      <SupportSessionContext.Provider value={supportToken}>
        {pathname.startsWith("/platform/support") && supportToken && supportOrganization && platformAdmin
          ? <Suspense fallback={<LoadingPage />}><AppShell platformAdmin supportOrganization={supportOrganization} onExitSupport={() => void exitSupport()} /></Suspense>
          : pathname === "/platform/orgs" && platformAdmin
            ? <Suspense fallback={<LoadingPage>Loading platform organizations…</LoadingPage>}><PlatformOrganizationsPage onEnterSupport={enterSupport} /></Suspense>
            : !orgId
              ? <Suspense fallback={<LoadingPage>Loading organizations…</LoadingPage>}><Routes><Route path="/organizations/create" element={<OrganizationCreatePage />} /><Route path="*" element={<OrganizationListPage />} /></Routes></Suspense>
              : contextResolved && !registered && (orgRole === "org:owner" || orgRole === "org:admin")
                ? <ProvisionOrganization />
                : pathname.startsWith("/organizations/profile")
                  ? <Suspense fallback={<LoadingPage>Loading organization profile…</LoadingPage>}><OrganizationProfilePage /></Suspense>
                : <Suspense fallback={<LoadingPage />}><AppShell platformAdmin={platformAdmin} /></Suspense>}
      </SupportSessionContext.Provider>
    </ApiContext.Provider>
    <Toaster position="bottom-right" />
  </TooltipProvider>;
}

export function App() {
  const { getToken } = useAuth();
  const api = useCallback(async <T,>(path: string, init?: RequestInit) => {
    return requestWithFreshToken<T>(getToken, path, init);
  }, [getToken]);
  return <ApiContext.Provider value={api}><AuthenticatedApp /></ApiContext.Provider>;
}
