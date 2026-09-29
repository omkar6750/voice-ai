import { useAuth, useClerk } from "@clerk/react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import type { OrganizationView } from "@/app/organizations";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ProviderCredentials } from "@/pages/settings/ProviderCredentials";

const OrganizationMembersPage = lazy(() =>
  import("./members").then((page) => ({ default: page.OrganizationMembersPage })),
);

export function OrganizationArea() {
  const { orgId: routeOrgId } = useParams();
  const { orgId: activeOrgId } = useAuth();
  const clerk = useClerk();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const api = useApi();
  const [organization, setOrganization] = useState<OrganizationView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!routeOrgId || routeOrgId !== activeOrgId) return;
    let cancelled = false;
    setOrganization(null);
    setError(null);
    void api<OrganizationView>(`/orgs/${routeOrgId}`)
      .then((value) => { if (!cancelled) { setOrganization(value); setError(null); } })
      .catch((cause) => { if (!cancelled) setError(cause instanceof Error ? cause.message : "Organization unavailable"); });
    return () => { cancelled = true; };
  }, [activeOrgId, api, routeOrgId]);

  async function switchToOrganization() {
    if (!routeOrgId) return;
    try {
      await clerk.setActive({ organization: routeOrgId });
      navigate(`/orgs/${routeOrgId}/settings`, { replace: true });
    } catch {
      toast.error("Could not switch organizations");
    }
  }

  if (!routeOrgId) return null;
  if (activeOrgId !== routeOrgId) return <main className="mx-auto max-w-3xl p-6"><Card><CardHeader><CardTitle>Switch organization</CardTitle><CardDescription>Confirm which organization you want to manage.</CardDescription></CardHeader><CardContent><Button onClick={() => void switchToOrganization()}>Switch to this organization</Button></CardContent></Card></main>;
  if (error) return <main className="mx-auto max-w-3xl p-6"><p role="alert" className="text-destructive">{error}</p><Button asChild variant="outline"><Link to="/orgs">Back to organizations</Link></Button></main>;
  if (!organization) return <main className="p-6" role="status">Loading organization…</main>;

  if (pathname.endsWith("/members")) return <Suspense fallback={<main className="p-6" role="status">Loading members…</main>}><OrganizationMembersPage /></Suspense>;

  const settings = pathname.endsWith("/settings");

  if (!settings) return <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
    <div>
      <p className="text-sm text-muted-foreground">{organization.role === "org:admin" ? "Organization admin" : "Organization member"}{organization.is_owner ? " · Owner" : ""}</p>
      <h1 className="text-2xl font-semibold">Welcome to {organization.name}</h1>
      <p className="text-sm text-muted-foreground">Your organization workspace is ready.</p>
    </div>
    <Card>
      <CardHeader><CardTitle>Workspace</CardTitle><CardDescription>Open the tools available to this organization.</CardDescription></CardHeader>
      <CardContent className="flex flex-wrap gap-3">
        <Button asChild><Link to="/runs">Open calls</Link></Button>
        <Button asChild variant="outline"><Link to={`/orgs/${routeOrgId}/members`}>View members</Link></Button>
        {organization.role === "org:admin" && <Button asChild variant="outline"><Link to={`/orgs/${routeOrgId}/settings`}>Organization settings</Link></Button>}
      </CardContent>
    </Card>
  </main>;

  return <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
    <div>
      <p className="text-sm text-muted-foreground">{organization.role === "org:admin" ? "Organization admin" : "Organization member"}{organization.is_owner ? " · Owner" : ""}</p>
      <h1 className="text-2xl font-semibold">{organization.name} settings</h1>
      <p className="text-sm text-muted-foreground">Manage access and the provider keys used by this organization.</p>
    </div>
    <Card>
      <CardHeader><CardTitle>People and access</CardTitle><CardDescription>Invite teammates, manage roles, or transfer ownership.</CardDescription></CardHeader>
      <CardContent><Button asChild variant="outline"><Link to={`/orgs/${routeOrgId}/members`}>Manage members</Link></Button></CardContent>
    </Card>
    <ProviderCredentials />
    <p className="text-sm text-muted-foreground">Agent, contact, and call features are enabled only for organizations whose data access has been provisioned.</p>
  </main>;
}
