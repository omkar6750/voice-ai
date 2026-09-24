import { useCallback, useState, type FormEvent } from "react";
import {
  Activity,
  AudioLines,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Settings2,
} from "lucide-react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { ApiContext, request } from "./api";
import { AgentEditor, AgentLanding, AgentsPage } from "../features/agents";
import { OverviewPage } from "../features/overview";
import { RunDetailPage, RunsPage } from "../features/runs";
import { SettingsPage } from "../features/settings";
import { Button, Input, Notice } from "../components/ui";

const navigation = [
  { label: "Overview", path: "/", icon: LayoutDashboard },
  { label: "Runs", path: "/runs", icon: Activity },
  { label: "Agents", path: "/agents", icon: AudioLines },
  { label: "Settings", path: "/settings", icon: Settings2 },
] as const;

function Connect({ onConnect }: { onConnect: (token: string) => void }) {
  const [candidate, setCandidate] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await request(candidate.trim(), "/providers");
      onConnect(candidate.trim());
      setCandidate("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12 text-foreground">
      <div className="w-full max-w-md rounded-lg border border-border bg-card p-7 shadow-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-white">
            <AudioLines size={22} />
          </div>
          <div>
            <p className="text-lg font-semibold tracking-tight">Voice AI</p>
            <p className="text-sm text-muted-foreground">Operator dashboard</p>
          </div>
        </div>
        <h1 className="text-xl font-semibold tracking-tight">
          Connect to workspace
        </h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Enter operator token. It stays in this tab’s memory.
        </p>
        <form className="mt-6 grid gap-4" onSubmit={submit}>
          <label className="grid gap-1.5 text-sm font-medium">
            Operator token
            <Input
              autoComplete="off"
              autoFocus
              required
              type="password"
              value={candidate}
              onChange={(event) => setCandidate(event.target.value)}
            />
          </label>
          {error && <Notice text={error} error />}
          <Button disabled={busy || !candidate.trim()} type="submit">
            <LockKeyhole size={16} />
            {busy ? "Connecting…" : "Connect"}
          </Button>
        </form>
      </div>
    </main>
  );
}

function Layout({ logout }: { logout: () => void }) {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const page = location.pathname.startsWith("/agents/")
    ? "Agent editor"
    : location.pathname.startsWith("/runs/")
      ? "Run details"
      : (navigation.find((item) => item.path === location.pathname)?.label ??
        "Dashboard");
  return (
    <div className="min-h-screen bg-background font-sans text-foreground">
      <div className="flex min-h-screen">
        <aside
          className={`sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-card md:flex ${collapsed ? "w-16" : "w-60"}`}
        >
          <Link
            to="/"
            className={`flex h-16 items-center gap-3 border-b border-border px-4 ${collapsed ? "justify-center" : ""}`}
          >
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-white">
              <AudioLines size={20} />
            </span>
            {!collapsed && (
              <span className="min-w-0">
                <span className="block text-sm font-semibold tracking-tight">
                  Voice AI
                </span>
                <span className="block text-xs text-muted-foreground">
                  Control plane
                </span>
              </span>
            )}
          </Link>
          <div className="flex-1 px-2 py-5">
            {!collapsed && (
              <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Workspace
              </p>
            )}
            <nav aria-label="Main navigation" className="grid gap-1">
              {navigation.map(({ label, path, icon: Icon }) => (
                <NavLink
                  key={path}
                  to={path}
                  end={path === "/"}
                  title={collapsed ? label : undefined}
                  className={({ isActive }) =>
                    `flex min-h-10 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors ${isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-secondary hover:text-foreground"} ${collapsed ? "justify-center" : ""}`
                  }
                >
                  <Icon size={18} strokeWidth={1.8} />
                  {!collapsed && label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="border-t border-border p-2">
            <button
              type="button"
              className="flex min-h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-muted-foreground hover:bg-secondary"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? (
                <ChevronRight size={18} />
              ) : (
                <ChevronLeft size={18} />
              )}
              {!collapsed && "Collapse"}
            </button>
            <button
              type="button"
              className="flex min-h-10 w-full items-center gap-3 rounded-md px-3 text-sm text-muted-foreground hover:bg-secondary"
              onClick={logout}
              aria-label="Disconnect"
            >
              <LogOut size={18} />
              {!collapsed && "Disconnect"}
            </button>
          </div>
        </aside>
        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-border bg-card/95 px-4 backdrop-blur-sm sm:px-6">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{page}</p>
              <p className="hidden text-xs text-muted-foreground sm:block">
                Single workspace
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden items-center gap-2 text-xs text-muted-foreground sm:inline-flex">
                <LockKeyhole size={14} />
                Operator session
              </span>
              <button
                type="button"
                onClick={logout}
                className="rounded-md p-2 text-muted-foreground hover:bg-secondary md:hidden"
                aria-label="Disconnect"
              >
                <LogOut size={18} />
              </button>
            </div>
          </header>
          <nav
            aria-label="Mobile navigation"
            className="flex gap-1 overflow-x-auto border-b border-border bg-card px-3 py-2 md:hidden"
          >
            {navigation.map(({ label, path, icon: Icon }) => (
              <NavLink
                key={path}
                to={path}
                end={path === "/"}
                className={({ isActive }) =>
                  `flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm ${isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"}`
                }
              >
                <Icon size={16} />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="mx-auto w-full max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/agents/:agentId" element={<AgentLanding />} />
              <Route
                path="/agents/:agentId/versions/:versionId"
                element={<AgentEditor />}
              />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route
                path="*"
                element={
                  <div className="grid min-h-72 place-items-center text-center">
                    <div>
                      <CircleHelp className="mx-auto mb-3 text-muted-foreground" />
                      <h1 className="text-xl font-semibold">Page not found</h1>
                      <Link
                        className="mt-3 inline-block text-sm text-primary hover:underline"
                        to="/"
                      >
                        Go to overview
                      </Link>
                    </div>
                  </div>
                }
              />
            </Routes>
          </div>
        </div>
      </div>
    </div>
  );
}

export function App() {
  const [token, setToken] = useState("");
  const api = useCallback(
    <T,>(path: string, init?: RequestInit) => request<T>(token, path, init),
    [token],
  );
  if (!token) return <Connect onConnect={setToken} />;
  return (
    <ApiContext.Provider value={api}>
      <Layout logout={() => setToken("")} />
    </ApiContext.Provider>
  );
}
