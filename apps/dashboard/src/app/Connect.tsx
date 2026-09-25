import { useState, type FormEvent } from "react";
import { Headphones } from "lucide-react";
import { toast } from "sonner";
import { request } from "./api";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

export function Connect({ onConnect }: { onConnect: (token: string) => void }) {
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
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not connect");
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
            Operator token remains in this tab's memory only.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="flex flex-col gap-4">
            <FieldGroup>
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
            </FieldGroup>
            <Button type="submit" disabled={busy || !candidate.trim()}>
              {busy ? "Connecting…" : "Connect"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
