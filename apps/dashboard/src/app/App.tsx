import { useCallback, useState } from "react";
import { ApiContext, OperatorTokenContext, request } from "./api";
import { AppShell } from "./AppShell";
import { Connect } from "./Connect";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

export function App() {
  const [token, setToken] = useState("");
  const api = useCallback(
    <T,>(path: string, init?: RequestInit) => request<T>(token, path, init),
    [token],
  );
  return (
    <TooltipProvider>
      <OperatorTokenContext.Provider value={token}>
        <ApiContext.Provider value={api}>
          {token ? (
            <AppShell disconnect={() => setToken("")} />
          ) : (
            <Connect onConnect={setToken} />
          )}
        </ApiContext.Provider>
      </OperatorTokenContext.Provider>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  );
}
