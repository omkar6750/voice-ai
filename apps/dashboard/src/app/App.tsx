import { SignIn, SignUp, useAuth, UserButton } from "@clerk/react";
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ApiContext, request } from "./api";
import { AppShell } from "./AppShell";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export function App() {
  const { getToken, isLoaded, isSignedIn, userId } = useAuth();
  const { pathname } = useLocation();
  const [accessStatus, setAccessStatus] = useState<"checking" | "allowed" | "denied">("checking");
  const [authorizedUserId, setAuthorizedUserId] = useState<string | null>(null);
  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;
    setAccessStatus("checking");
    setAuthorizedUserId(null);
    void (async () => {
      try {
        const sessionToken = await getToken();
        if (!sessionToken) throw new Error("No Clerk session token");
        await request(sessionToken, "/auth/legacy-access");
        if (!cancelled) {
          setAuthorizedUserId(userId);
          setAccessStatus("allowed");
        }
      } catch {
        if (!cancelled) setAccessStatus("denied");
      }
    })();
    return () => { cancelled = true; };
  }, [getToken, isSignedIn, userId]);
  const api = useCallback(
    async <T,>(path: string, init?: RequestInit) => {
      const sessionToken = await getToken();
      if (!sessionToken) throw new Error("Sign in required");
      return request<T>(sessionToken, path, init);
    },
    [getToken],
  );
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
            <p className="max-w-xl text-muted-foreground">Create an organization, invite teammates, and manage agents across workspaces. Customer onboarding is being connected to the existing runtime.</p>
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
        {accessStatus === "allowed" && authorizedUserId === userId ? <AppShell /> : (
          <main className="grid min-h-svh place-items-center px-4">
            <div className="space-y-4 text-center">
              <div className="mx-auto w-fit"><UserButton /></div>
              <p role="status" className="text-sm text-muted-foreground">
                {accessStatus === "checking" ? "Checking workspace access…" : "This account is not assigned to the existing workspace. Sign in with its verified owner email."}
              </p>
            </div>
          </main>
        )}
      </ApiContext.Provider>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  );
}
