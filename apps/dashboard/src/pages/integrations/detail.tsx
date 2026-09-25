import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import {
  LoadState,
  PageBody,
  PageHeader,
  ReadOnlyValue,
  StatusBadge,
} from "@/components/record-page";
import { Button } from "@/components/ui/button";
import { useResource } from "@/lib/resources";
import { MediaPanel } from "./MediaPanel";
import { SecretsPanel } from "./SecretsPanel";
import type { Connection } from "./index";

type Template = {
  name: string;
  status?: string;
  language?: string;
  category?: string;
};
const sections = ["Account", "Credentials", "Media", "Templates"] as const;
export function IntegrationDetailPage() {
  const { connectionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const api = useApi();
  const { data, loading, error, reload } = useResource<{
    connections: Connection[];
  }>("/integrations");
  const connection = data?.connections.find((item) => item.id === connectionId);
  const section =
    sections.find((item) => item.toLowerCase() === params.get("section")) ??
    "Account";
  const [templates, setTemplates] = useState<Template[] | null>(null);
  const [templateBusy, setTemplateBusy] = useState(false);
  async function loadTemplates() {
    setTemplateBusy(true);
    try {
      const response = await api<{ templates: Template[] }>(
        `/integrations/${connectionId}/templates`,
      );
      setTemplates(response.templates);
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : "Could not load templates from Meta",
      );
    } finally {
      setTemplateBusy(false);
    }
  }
  return (
    <PageBody>
      <PageHeader
        title={connection?.label ?? "Integration"}
        description="WhatsApp account settings and media. Secrets stay on the server."
        action={
          <Button asChild variant="outline">
            <Link to="/integrations">All integrations</Link>
          </Button>
        }
      />
      <LoadState
        loading={loading}
        error={error}
        empty={!connection ? "Connection not found." : undefined}
      >
        {connection && (
          <>
            <nav
              aria-label="Integration sections"
              className="flex flex-wrap gap-1 border-b pb-2"
            >
              {sections.map((item) => (
                <Button
                  type="button"
                  size="sm"
                  key={item}
                  variant={section === item ? "secondary" : "ghost"}
                  onClick={() => setParams({ section: item.toLowerCase() })}
                >
                  {item}
                </Button>
              ))}
            </nav>
            {section === "Account" && (
              <section className="max-w-2xl">
                <ReadOnlyValue label="Provider" value={connection.provider} />
                <ReadOnlyValue
                  label="Enabled"
                  value={
                    <StatusBadge
                      value={connection.enabled ? "enabled" : "disabled"}
                    />
                  }
                  reason="Connection updates need PATCH API. Current POST creates disabled accounts."
                />
                <ReadOnlyValue
                  label="Phone number ID"
                  value={connection.config.phone_number_id}
                />
                <ReadOnlyValue
                  label="WABA ID"
                  value={connection.config.waba_id}
                />
                <ReadOnlyValue
                  label="Meta API version"
                  value={connection.config.api_version}
                />
                <ReadOnlyValue
                  label="Configured secrets"
                  value={connection.secret_names.join(", ") || "None"}
                />
              </section>
            )}
            {section === "Credentials" && (
              <SecretsPanel
                connectionId={connectionId}
                configured={connection.secret_names}
                reload={reload}
              />
            )}
            {section === "Media" && <MediaPanel connectionId={connectionId} />}
            {section === "Templates" && (
              <section className="flex max-w-2xl flex-col gap-4">
                <div>
                  <h2 className="text-base font-semibold">Meta templates</h2>
                  <p className="text-xs text-muted-foreground">
                    Fetched from Meta on demand. Not a local template editor.
                  </p>
                </div>
                <Button
                  className="self-start"
                  variant="outline"
                  disabled={templateBusy}
                  onClick={() => void loadTemplates()}
                >
                  {templateBusy ? "Loading…" : "Load templates"}
                </Button>
                {templates?.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    No templates returned.
                  </p>
                )}
                {templates?.map((template) => (
                  <div
                    key={`${template.name}-${template.language}`}
                    className="flex justify-between gap-3 border-b py-2 text-sm"
                  >
                    <span className="font-medium">
                      {template.name} · {template.language}
                    </span>
                    <span className="text-muted-foreground">
                      {template.status ?? "Unknown"}
                    </span>
                  </div>
                ))}
              </section>
            )}
          </>
        )}
      </LoadState>
    </PageBody>
  );
}
