import { SignIn, SignUp, useAuth, UserButton } from "@clerk/react";
import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ApiContext, OperatorTokenContext, request } from "./api";
import { AppShell } from "./AppShell";
import { Connect } from "./Connect";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export function App() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { pathname } = useLocation();
  const [token, setToken] = useState("");
  const [identityStatus, setIdentityStatus] = useState<"checking" | "verified" | "unavailable">("checking");
  useEffect(() => {
    if (!isSignedIn) return;
    let cancelled = false;
    setIdentityStatus("checking");
    void (async () => {
      try {
        const sessionToken = await getToken();
        if (!sessionToken) throw new Error("No Clerk session token");
        await request(sessionToken, "/auth/me");
        if (!cancelled) setIdentityStatus("verified");
      } catch {
        if (!cancelled) setIdentityStatus("unavailable");
      }
    })();
    return () => { cancelled = true; };
  }, [getToken, isSignedIn]);
  const api = useCallback(
    <T,>(path: string, init?: RequestInit) => request<T>(token, path, init),
    [token],
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
      <OperatorTokenContext.Provider value={token}>
        <ApiContext.Provider value={api}>
          {token ? (
            <AppShell disconnect={() => setToken("")} />
          ) : (
            <>
              <div className="absolute right-4 top-4"><UserButton /></div>
              <Connect onConnect={setToken} identityStatus={identityStatus} />
            </>
          )}
        </ApiContext.Provider>
      </OperatorTokenContext.Provider>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  );
}
