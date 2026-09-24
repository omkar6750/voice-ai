import { lazy, Suspense, useCallback, useState, type FormEvent } from "react";
import {
  Activity,
  AudioLines,
  CalendarClock,
  Database,
  Headphones,
  Link2,
  ListTodo,
  LogOut,
  Radio,
  Settings2,
  Users,
} from "lucide-react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { toast } from "sonner";
import { ApiContext, OperatorTokenContext, request } from "./api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { Spinner } from "@/components/ui/spinner";
import { Skeleton } from "@/components/ui/skeleton";
import { PlaceholderPage } from "@/pages/placeholder";

const RunsPage = lazy(() =>
  import("@/pages/runs").then((module) => ({ default: module.RunsPage })),
);
const RunDetailPage = lazy(() =>
  import("@/pages/runs/detail").then((module) => ({
    default: module.RunDetailPage,
  })),
);
const AgentsPage = lazy(() =>
  import("@/pages/agents").then((module) => ({ default: module.AgentsPage })),
);
const AgentDetailPage = lazy(() =>
  import("@/pages/agents/detail").then((module) => ({
    default: module.AgentDetailPage,
  })),
);
const AgentVersionPage = lazy(() =>
  import("@/pages/agent-version").then((module) => ({
    default: module.AgentVersionPage,
  })),
);
const ContactsPage = lazy(() =>
  import("@/pages/contacts").then((module) => ({
    default: module.ContactsPage,
  })),
);
const KnowledgePage = lazy(() =>
  import("@/pages/knowledge").then((module) => ({
    default: module.KnowledgePage,
  })),
);
const KnowledgeDetailPage = lazy(() =>
  import("@/pages/knowledge/detail").then((module) => ({
    default: module.KnowledgeDetailPage,
  })),
);
const ToolsPage = lazy(() =>
  import("@/pages/tools").then((module) => ({ default: module.ToolsPage })),
);
const IntegrationsPage = lazy(() =>
  import("@/pages/integrations").then((module) => ({
    default: module.IntegrationsPage,
  })),
);
const CallbacksPage = lazy(() =>
  import("@/pages/callbacks").then((module) => ({
    default: module.CallbacksPage,
  })),
);
const EndpointsPage = lazy(() =>
  import("@/pages/endpoints").then((module) => ({
    default: module.EndpointsPage,
  })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings").then((module) => ({
    default: module.SettingsPage,
  })),
);

import { QuickDialer } from "@/components/quick-dialer";

const navigation = [
  { title: "Runs", path: "/runs", icon: Activity },
  { title: "Agents", path: "/agents", icon: AudioLines },
  { title: "Contacts", path: "/contacts", icon: Users },
  { title: "Knowledge", path: "/knowledge", icon: Database },
  { title: "Tools", path: "/tools", icon: ListTodo },
  { title: "Integrations", path: "/integrations", icon: Link2 },
  { title: "Callbacks", path: "/callbacks", icon: CalendarClock },
  { title: "Endpoints", path: "/endpoints", icon: Radio },
  { title: "Settings", path: "/settings", icon: Settings2 },
] as const;

function Connect({ onConnect }: { onConnect: (token: string) => void }) {
  const [candidate, setCandidate] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await request(candidate.trim(), "/providers");
      onConnect(candidate.trim());
      setCandidate("");
      toast.success("Workspace connected");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not connect");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="grid min-h-svh place-items-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Headphones aria-hidden="true" /> Voice AI
          </CardTitle>
          <CardDescription>
            Enter operator token to inspect runs. Token stays in this tab's
            memory.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submit}>
            <Field>
              <FieldLabel htmlFor="operator-token">Operator token</FieldLabel>
              <Input
                id="operator-token"
                type="password"
                autoComplete="off"
                autoFocus
                required
                value={candidate}
                onChange={(event) => setCandidate(event.target.value)}
              />
            </Field>
            <Button type="submit" disabled={busy || !candidate.trim()}>
              {busy && <Spinner data-icon="inline-start" />}
              {busy ? "Connecting…" : "Connect"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function AppSidebar({ logout }: { logout: () => void }) {
  const location = useLocation();
  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <Link
          to="/runs"
          className="flex min-h-10 items-center gap-2 px-2 font-semibold"
        >
          <AudioLines aria-hidden="true" className="size-4 text-emerald-600" />
          <span className="group-data-[collapsible=icon]:hidden">Voice AI</span>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Workspace</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation.map(({ title, path, icon: Icon }) => (
                <SidebarMenuItem key={path}>
                  <SidebarMenuButton
                    asChild
                    isActive={
                      location.pathname === path ||
                      location.pathname.startsWith(path + "/")
                    }
                    tooltip={title}
                  >
                    <NavLink to={path}>
                      <Icon aria-hidden="true" />
                      <span>{title}</span>
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={logout} tooltip="Disconnect">
              <LogOut aria-hidden="true" />
              <span>Disconnect</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

function Workspace({ logout }: { logout: () => void }) {
  const location = useLocation();
  const part = navigation.find(
    (item) =>
      location.pathname === item.path ||
      location.pathname.startsWith(item.path + "/"),
  );
  const runId = location.pathname.startsWith("/runs/")
    ? location.pathname.split("/")[2]
    : null;
  return (
    <SidebarProvider>
      <AppSidebar logout={logout} />
      <SidebarInset className="min-w-0">
        <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
          <div className="flex items-center gap-3">
            <SidebarTrigger />
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink asChild>
                    <Link to="/runs">Voice AI</Link>
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  {runId ? (
                    <BreadcrumbLink asChild>
                      <Link to="/runs">Runs</Link>
                    </BreadcrumbLink>
                  ) : (
                    <BreadcrumbPage>{part?.title ?? "Page"}</BreadcrumbPage>
                  )}
                </BreadcrumbItem>
                {runId && (
                  <>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                      <BreadcrumbPage className="max-w-40 truncate">
                        {runId.slice(0, 8)}
                      </BreadcrumbPage>
                    </BreadcrumbItem>
                  </>
                )}
              </BreadcrumbList>
            </Breadcrumb>
          </div>

          <div className="flex items-center gap-2">
            <QuickDialer />
          </div>
        </header>
        <div className="min-w-0 flex-1">
          <Suspense
            fallback={
              <div className="flex flex-col gap-3 p-6">
                <Skeleton className="h-8 w-40" />
                <Skeleton className="h-64 w-full" />
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<Navigate to="/runs" replace />} />
              <Route path="/runs" element={<RunsPage />} />
              <Route path="/runs/:runId" element={<RunDetailPage />} />

              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/agents/:agentId" element={<AgentDetailPage />} />
              <Route
                path="/agents/:agentId/versions/:versionId"
                element={<AgentVersionPage />}
              />

              <Route path="/contacts" element={<ContactsPage />} />

              <Route path="/knowledge" element={<KnowledgePage />} />
              <Route path="/knowledge/:kbId" element={<KnowledgeDetailPage />} />

              <Route path="/tools" element={<ToolsPage />} />
              <Route path="/integrations" element={<IntegrationsPage />} />
              <Route path="/callbacks" element={<CallbacksPage />} />
              <Route path="/endpoints" element={<EndpointsPage />} />
              <Route path="/settings" element={<SettingsPage />} />

              <Route
                path="*"
                element={<PlaceholderPage title="Page not found" />}
              />
            </Routes>
          </Suspense>
        </div>
      </SidebarInset>
    </SidebarProvider>
  );
}

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
            <Workspace logout={() => setToken("")} />
          ) : (
            <Connect onConnect={setToken} />
          )}
        </ApiContext.Provider>
      </OperatorTokenContext.Provider>
      <Toaster position="bottom-right" />
    </TooltipProvider>
  );
}
