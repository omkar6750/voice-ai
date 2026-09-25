import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { PendingPage } from "@/pages/PendingPage";

const RunsPage = lazy(() =>
  import("@/pages/runs").then((page) => ({ default: page.RunsPage })),
);
const RunDetailPage = lazy(() =>
  import("@/pages/runs/detail").then((page) => ({
    default: page.RunDetailPage,
  })),
);
const AgentsPage = lazy(() =>
  import("@/pages/agents").then((page) => ({ default: page.AgentsPage })),
);
const AgentDetailPage = lazy(() =>
  import("@/pages/agents/detail").then((page) => ({
    default: page.AgentDetailPage,
  })),
);
const AgentEditorPage = lazy(() =>
  import("@/pages/agents/AgentEditorPage").then((page) => ({
    default: page.AgentEditorPage,
  })),
);
const ContactsPage = lazy(() =>
  import("@/pages/contacts").then((page) => ({ default: page.ContactsPage })),
);
const KnowledgePage = lazy(() =>
  import("@/pages/knowledge").then((page) => ({ default: page.KnowledgePage })),
);
const KnowledgeDetailPage = lazy(() =>
  import("@/pages/knowledge/detail").then((page) => ({
    default: page.KnowledgeDetailPage,
  })),
);
const ToolsPage = lazy(() =>
  import("@/pages/tools").then((page) => ({ default: page.ToolsPage })),
);
const ToolDetailPage = lazy(() =>
  import("@/pages/tools/detail").then((page) => ({
    default: page.ToolDetailPage,
  })),
);
const IntegrationsPage = lazy(() =>
  import("@/pages/integrations").then((page) => ({
    default: page.IntegrationsPage,
  })),
);
const IntegrationDetailPage = lazy(() =>
  import("@/pages/integrations/detail").then((page) => ({
    default: page.IntegrationDetailPage,
  })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings").then((page) => ({ default: page.SettingsPage })),
);

export function AppRoutes() {
  return (
    <Suspense
      fallback={
        <div className="flex flex-col gap-3 p-6">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-48 w-full" />
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
          element={<AgentEditorPage />}
        />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/knowledge/:baseId" element={<KnowledgeDetailPage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/tools/:toolId" element={<ToolDetailPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route
          path="/integrations/:connectionId"
          element={<IntegrationDetailPage />}
        />
        {/* TODO(API): GET /callbacks with callback ID, contact, pinned version, due time, status, claim and resulting run. */}
        <Route
          path="/callbacks"
          element={
            <PendingPage
              title="Callbacks"
              reason="Scheduling and launch routes exist, but no callback list route exists yet. No queue or count is invented."
            />
          }
        />
        {/* TODO(API): GET /runtime-endpoints with saved config, active claim, health snapshot and readiness. */}
        <Route
          path="/endpoints"
          element={
            <PendingPage
              title="Endpoints"
              reason="Endpoint registration exists, but the API cannot list endpoints or their live modem status yet."
            />
          }
        />
        <Route path="/settings" element={<SettingsPage />} />
        <Route
          path="*"
          element={
            <PendingPage
              title="Page not found"
              reason="No route exists for this address."
            />
          }
        />
      </Routes>
    </Suspense>
  );
}
