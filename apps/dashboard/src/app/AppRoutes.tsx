import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Skeleton } from "@/components/ui/skeleton";
import { PendingPage } from "@/pages/PendingPage";

const RunsPage = lazy(() =>
  import("@/pages/runs").then((page) => ({ default: page.RunsPage })),
);
const RecordingsPage = lazy(() =>
  import("@/pages/recordings").then((page) => ({
    default: page.RecordingsPage,
  })),
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
const ContactDetailPage = lazy(() =>
  import("@/pages/contacts/detail").then((page) => ({
    default: page.ContactDetailPage,
  })),
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
const ToolVersionPage = lazy(() =>
  import("@/pages/tools/ToolVersionPage").then((page) => ({
    default: page.ToolVersionPage,
  })),
);
const IntegrationsPage = lazy(() =>
  import("@/pages/integrations").then((page) => ({
    default: page.IntegrationsPage,
  })),
);
const WhatsAppIntegrationsPage = lazy(() =>
  import("@/pages/integrations/provider").then((page) => ({
    default: page.WhatsAppIntegrationsPage,
  })),
);
const TwilioIntegrationsPage = lazy(() =>
  import("@/pages/integrations/provider").then((page) => ({
    default: page.TwilioIntegrationsPage,
  })),
);
const CalendarIntegrationsPage = lazy(() =>
  import("@/pages/integrations/provider").then((page) => ({
    default: page.CalendarIntegrationsPage,
  })),
);
const IntegrationDetailPage = lazy(() =>
  import("@/pages/integrations/detail").then((page) => ({
    default: page.IntegrationDetailPage,
  })),
);
const CallbacksPage = lazy(() =>
  import("@/pages/callbacks").then((page) => ({ default: page.CallbacksPage })),
);
const EndpointsPage = lazy(() =>
  import("@/pages/endpoints").then((page) => ({ default: page.EndpointsPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings").then((page) => ({ default: page.SettingsPage })),
);
const CredentialsSettingsPage = lazy(() =>
  import("@/pages/settings/ProviderCredentials").then((page) => ({
    default: page.CredentialsSettingsPage,
  })),
);

export function AppRoutes({ platformAdmin }: { platformAdmin: boolean }) {
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
        <Route
          path="/platform/support"
          element={<Navigate to="/runs" replace />}
        />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/recordings" element={<RecordingsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/agents/:agentId" element={<AgentDetailPage />} />
        <Route
          path="/agents/:agentId/versions/:versionId"
          element={<AgentEditorPage />}
        />
        <Route path="/contacts" element={<ContactsPage />} />
        <Route path="/contacts/:contactId" element={<ContactDetailPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/knowledge/:baseId" element={<KnowledgeDetailPage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/tools/:toolId" element={<ToolDetailPage />} />
        <Route
          path="/tools/:toolId/versions/:versionId"
          element={<ToolVersionPage />}
        />
        <Route
          path="/tools/:toolId/versions/:versionId/edit"
          element={<ToolVersionPage />}
        />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route
          path="/integrations/whatsapp"
          element={<WhatsAppIntegrationsPage />}
        />
        <Route
          path="/integrations/twilio"
          element={<TwilioIntegrationsPage />}
        />
        <Route
          path="/integrations/calendar"
          element={<CalendarIntegrationsPage />}
        />
        <Route
          path="/integrations/:connectionId"
          element={<IntegrationDetailPage />}
        />
        <Route path="/callbacks" element={<CallbacksPage />} />
        <Route
          path="/endpoints"
          element={
            platformAdmin ? <EndpointsPage /> : <Navigate to="/runs" replace />
          }
        />

        <Route
          path="/settings"
          element={<Navigate to="/settings/organization" replace />}
        />
        <Route path="/settings/organization" element={<SettingsPage />} />
        <Route
          path="/settings/credentials"
          element={<CredentialsSettingsPage />}
        />
        <Route
          path="/orgs/:orgId/*"
          element={<Navigate to="/organizations/profile" replace />}
        />
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
