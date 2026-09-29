import { useState } from "react";
import { useClerk } from "@clerk/react";
import { Link, useNavigate } from "react-router-dom";
import { useApi } from "@/app/api";
import type { AccountView, OrganizationView } from "@/app/organizations";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export function CreateOrganizationPage({ account }: { account: AccountView | null }) {
  const api = useApi();
  const clerk = useClerk();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setPending(true);
    setError(null);
    try {
      const organization = await api<OrganizationView>("/orgs", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      await clerk.setActive({ organization: organization.id });
      navigate("/orgs", { replace: true });
      window.location.reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create organization");
    } finally {
      setPending(false);
    }
  }

  const allowed = Boolean(account?.can_create_org && account.organization_creation_enabled);
  return (
    <main className="mx-auto flex min-h-svh max-w-xl items-center px-6 py-12">
      <Card className="w-full">
        <CardHeader>
          <CardTitle>Create your organization</CardTitle>
          <CardDescription>Your organization is your shared account for agents, contacts, tools, and call history. You can join other organizations by invitation later.</CardDescription>
        </CardHeader>
        <CardContent>
          {!allowed ? <div className="flex flex-col gap-4">
            <p className="text-sm text-muted-foreground">Organization creation is not available for this account right now. You can still open an organization you have joined.</p>
            <Button variant="outline" asChild><Link to="/orgs">Back to organizations</Link></Button>
          </div> : <FieldGroup>
            <Field>
              <FieldLabel htmlFor="organization-name">Organization name</FieldLabel>
              <Input id="organization-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} autoComplete="organization" />
              <FieldDescription>You can change the display name later.</FieldDescription>
            </Field>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div className="flex gap-2">
              <Button disabled={pending || name.trim().length < 2} onClick={() => void create()}>{pending ? "Creating…" : "Create organization"}</Button>
              <Button variant="outline" asChild><Link to="/orgs">Cancel</Link></Button>
            </div>
          </FieldGroup>}
        </CardContent>
      </Card>
    </main>
  );
}
