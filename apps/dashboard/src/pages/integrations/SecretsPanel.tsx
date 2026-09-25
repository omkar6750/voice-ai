import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";
import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";

const names = ["access_token", "app_secret", "verify_token"] as const;
export function SecretsPanel({
  connectionId,
  configured,
  reload,
}: {
  connectionId: string;
  configured: string[];
  reload: () => Promise<unknown>;
}) {
  const api = useApi();
  const [name, setName] = useState<(typeof names)[number]>("access_token");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`/integrations/${connectionId}/secrets/${name}`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      });
      setValue("");
      toast.success("Credential saved. Value is not returned.");
      await reload();
    } catch (cause) {
      toast.error(
        cause instanceof Error ? cause.message : "Could not store credential",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="flex max-w-2xl flex-col gap-5">
      <div>
        <h2 className="text-base font-semibold">Credentials</h2>
        <p className="text-xs text-muted-foreground">
          Write-only. Server encrypts these with its environment keyring.
        </p>
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {names.map((item) => (
          <Button
            key={item}
            variant={name === item ? "secondary" : "outline"}
            size="sm"
            onClick={() => {
              setName(item);
              setValue("");
            }}
          >
            {item.replaceAll("_", " ")}{" "}
            {configured.includes(item) ? "· set" : "· missing"}
          </Button>
        ))}
      </div>
      <form onSubmit={save}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="integration-secret">
              Replace {name.replaceAll("_", " ")}
            </FieldLabel>
            <Input
              id="integration-secret"
              type="password"
              autoComplete="off"
              value={value}
              onChange={(event) => setValue(event.target.value)}
              required
            />
            <FieldDescription>
              Existing value is never shown or prefilled.
            </FieldDescription>
          </Field>
        </FieldGroup>
        <Button className="mt-4" type="submit" disabled={busy || !value}>
          {busy ? "Saving…" : "Save credential"}
        </Button>
      </form>
    </section>
  );
}
