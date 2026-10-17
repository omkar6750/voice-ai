import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useApi } from "./api";

type Names = { firstName: string; lastName: string };

export function OrganizationSetup({ orgId, orgName, firstName, lastName, saveProfile }: {
  orgId: string;
  orgName: string;
  firstName: string | null;
  lastName: string | null;
  saveProfile: (names: Names) => Promise<unknown>;
}) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [names, setNames] = useState({ firstName: firstName ?? "", lastName: lastName ?? "" });
  const needsNames = !firstName?.trim() || !lastName?.trim();
  // Also fence React StrictMode's repeated effect setup before mutation state updates.
  const attempted = useRef(false);
  const { mutate, isPending, isSuccess, isError, error } = useMutation({
    retry: false,
    mutationFn: async (profile: Names | undefined) => {
      if (profile) await saveProfile(profile);
      return api(`/orgs/${orgId}/provision`, {
        method: "POST",
        body: JSON.stringify({ name: orgName }),
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["app-context"] }),
  });
  useEffect(() => {
    if (!needsNames && !attempted.current) {
      attempted.current = true;
      mutate(undefined);
    }
  }, [needsNames, mutate]);

  return <main className="mx-auto flex min-h-svh max-w-xl flex-col justify-center gap-6 p-8">
    <h1 className="text-xl font-semibold">Set up {orgName}</h1>
    {isError && <Alert variant="destructive">
      <AlertTitle>Organization setup failed</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>}
    {needsNames && !isSuccess ? <form className="flex flex-col gap-6" onSubmit={(event) => {
      event.preventDefault();
      const profile = { firstName: names.firstName.trim(), lastName: names.lastName.trim() };
      if (isPending || !profile.firstName || !profile.lastName) return;
      attempted.current = true;
      mutate(profile);
    }}>
      <p>Add your first and last name to your Clerk profile to finish setting up your organization.</p>
      <FieldGroup>
        <Field><FieldLabel htmlFor="setup-first-name">First name</FieldLabel>
          <Input id="setup-first-name" autoComplete="given-name" required disabled={isPending} value={names.firstName} onChange={(event) => setNames({ ...names, firstName: event.target.value })} />
        </Field>
        <Field><FieldLabel htmlFor="setup-last-name">Last name</FieldLabel>
          <Input id="setup-last-name" autoComplete="family-name" required disabled={isPending} value={names.lastName} onChange={(event) => setNames({ ...names, lastName: event.target.value })} />
        </Field>
      </FieldGroup>
      <Button type="submit" disabled={isPending || !names.firstName.trim() || !names.lastName.trim()}>{isPending ? "Setting up…" : "Save profile and continue"}</Button>
    </form> : isError ? <Button onClick={() => mutate(undefined)} disabled={isPending}>Retry organization setup</Button>
      : <p role="status">Setting up organization…</p>}
  </main>;
}
