import { useCallback, useEffect, useState } from "react";
import { useApi } from "@/app/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import type { components } from "@/generated/api";

type PlatformOrganization = components["schemas"]["PlatformOrganizationView"];

export function PlatformOrganizationsPage({ onEnterSupport }: { onEnterSupport: (id: string, name: string) => Promise<void> }) {
  const api = useApi();
  const [organizations, setOrganizations] = useState<PlatformOrganization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOrganizations(await api<PlatformOrganization[]>("/platform/orgs"));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not load organizations");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => { void load(); }, [load]);

  return <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
    <div>
      <Badge variant="secondary">Platform administrator</Badge>
      <h1 className="mt-2 text-2xl font-semibold">Organization directory</h1>
      <p className="text-sm text-muted-foreground">Registered customer organizations. This directory does not grant access to their data.</p>
    </div>
    <Card>
      <CardHeader>
        <CardTitle>Customer organizations</CardTitle>
        <CardDescription>Names and ownership references are shown for support triage.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {loading && <p role="status" className="text-sm text-muted-foreground">Loading organizations…</p>}
        {error && <div className="flex flex-col items-start gap-3"><p role="alert" className="text-sm text-destructive">{error}</p><Button variant="outline" onClick={() => void load()}>Retry</Button></div>}
        {!loading && !error && organizations.length === 0 && <p className="text-sm text-muted-foreground">No registered organizations yet.</p>}
        {!loading && !error && organizations.map((organization) => {
          const { id, name, owner_name: ownerName, owner_user_id: ownerId } = organization;
          return <article key={id} className="flex flex-col gap-2 rounded-lg border p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <h2 className="font-medium">{name}</h2>
              <p className="truncate text-xs text-muted-foreground">{id}</p>
              <p className="text-sm text-muted-foreground">Owner: {ownerName ?? ownerId ?? "Unknown"}</p>
            </div>
            <Button variant="outline" onClick={() => void onEnterSupport(id, name)}>Enter support session</Button>
          </article>;
        })}
      </CardContent>
    </Card>
  </main>;
}
