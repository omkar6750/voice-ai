import { UserButton, useClerk } from "@clerk/react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { OrganizationView } from "./organizations";

export function OrgExplorer({
  organizations,
  loading,
  error,
  canCreate,
  availableOrgIds,
  platformAdmin,
}: {
  organizations: OrganizationView[];
  loading: boolean;
  error: string | null;
  canCreate: boolean;
  availableOrgIds: string[];
  platformAdmin: boolean;
}) {
  const clerk = useClerk();
  const navigate = useNavigate();
  const [switching, setSwitching] = useState<string | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);

  async function select(id: string) {
    setSwitching(id);
    setSwitchError(null);
    try {
      await clerk.setActive({ organization: id });
      navigate(availableOrgIds.includes(id) ? "/runs" : `/orgs/${id}`);
    } catch {
      setSwitchError("Could not switch organizations. Please try again.");
    } finally {
      setSwitching(null);
    }
  }

  return (
    <main className="mx-auto flex min-h-svh max-w-3xl flex-col gap-6 px-6 py-16">
      <div className="flex justify-end"><UserButton /></div>
      <div>
        <p className="text-sm font-medium text-muted-foreground">Voice AI</p>
        <h1 className="mt-2 text-3xl font-semibold">Your organizations</h1>
        <p className="mt-2 text-muted-foreground">Only organizations you have joined appear here. Accept an invitation from its email link to join another.</p>
      </div>
      {canCreate && <Button className="self-start" onClick={() => navigate("/onboarding/create-org")}>Create your organization</Button>}
      {platformAdmin && <Button className="self-start" variant="outline" onClick={() => navigate("/platform/orgs")}>Platform organization directory</Button>}
      {loading && <p role="status">Loading organizations…</p>}
      {error && <p role="alert" className="text-destructive">{error}</p>}
      {switchError && <p role="alert" className="text-destructive">{switchError}</p>}
      {!loading && !error && organizations.length === 0 && (
        <Card><CardContent className="pt-6 text-muted-foreground">You have not joined an organization yet. Ask an admin to invite your email address.</CardContent></Card>
      )}
      <div className="grid gap-3">
        {organizations.map((org) => (
          <Card key={org.id}>
            <CardHeader><CardTitle>{org.name}</CardTitle></CardHeader>
            <CardContent className="flex items-center justify-between gap-4">
              <p className="text-sm text-muted-foreground">{org.is_owner ? "Owner" : org.role === "org:admin" ? "Admin" : "Member"}{!org.registered && " · Setup pending"}</p>
              <Button onClick={() => void select(org.id)} disabled={switching !== null || !org.registered}>
                {!org.registered ? "Setup pending" : switching === org.id ? "Switching…" : availableOrgIds.includes(org.id) ? "Open app" : "Manage organization"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
