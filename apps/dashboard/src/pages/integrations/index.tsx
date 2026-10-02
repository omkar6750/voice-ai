import { useResource } from "@/lib/resources";
import { ArrowUpRight, CalendarDays, MessageCircle, Phone } from "lucide-react";
import { Link } from "react-router-dom";
import { PageBody, PageHeader } from "@/components/record-page";

export type Connection = {
  id: string;
  label: string;
  provider: "whatsapp" | "twilio_voice";
  enabled: boolean;
  config: Record<string, any>;
  secret_names: string[];
  updated_at?: string;
  created_at?: string;
  webhook_url?: string | null;
  deleted_at?: string | null;
  credential_id?: string | null;
};
type CalendarIntegration = { id: string; status: string };

const sections = [
  {
    id: "whatsapp",
    title: "WhatsApp",
    detail: "Messaging, templates, and media",
    href: "/integrations/whatsapp",
    icon: MessageCircle,
  },
  {
    id: "twilio",
    title: "Twilio Voice",
    detail: "Calling numbers and voice credentials",
    href: "/integrations/twilio",
    icon: Phone,
  },
  {
    id: "calendar",
    title: "Calendar",
    detail: "Google Calendars for callback scheduling",
    href: "/integrations/calendar",
    icon: CalendarDays,
  },
] as const;

export function IntegrationsPage() {
  const connections = useResource<{ connections: Connection[] }>(
    "/integrations",
  );
  const calendars = useResource<{ integrations: CalendarIntegration[] }>(
    "/calendar-integrations",
  );
  const rows = sections.map((section) => {
    if (section.id === "calendar") {
      const all = calendars.data?.integrations ?? [];
      const count = all.filter((item) => item.status === "connected").length;
      return {
        ...section,
        count,
        total: all.length,
        status: count
          ? "Connected"
          : all.length
            ? "Reconnect needed"
            : "Not connected",
      };
    }
    const provider = section.id === "twilio" ? "twilio_voice" : "whatsapp";
    const all = (connections.data?.connections ?? []).filter(
      (item) => item.provider === provider && !item.deleted_at,
    );
    return {
      ...section,
      count: all.length,
      total: all.length,
      status: all.some((item) => item.enabled)
        ? "Active"
        : all.length
          ? "Needs attention"
          : "Not connected",
    };
  });

  return (
    <PageBody>
      <PageHeader
        title="Integrations"
        description="Manage each provider in its own workspace."
      />
      <div className="divide-y border-y">
        {rows.map(
          ({ id, title, detail, href, icon: Icon, count, total, status }) => (
            <Link
              key={id}
              to={href}
              className="group flex flex-wrap items-center gap-4 py-5 transition-colors hover:bg-muted/30"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground">
                <Icon className="size-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{title}</span>
                <span className="mt-1 block text-sm text-muted-foreground">
                  {detail}
                </span>
              </span>
              <span className="min-w-28 text-sm text-muted-foreground">
                {count}
                {id === "calendar"
                  ? ` connected${total > count ? ` · ${total - count} disconnected` : ""}`
                  : ` connection${count === 1 ? "" : "s"}`}
              </span>
              <span className="w-32 text-sm">{status}</span>
              <ArrowUpRight className="size-4 text-muted-foreground transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
            </Link>
          ),
        )}
      </div>
    </PageBody>
  );
}
