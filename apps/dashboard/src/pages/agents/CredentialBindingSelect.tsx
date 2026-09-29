import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/react";
import { useApi } from "@/app/api";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import type { components } from "@/generated/api";
import type { AgentConfig } from "./types";

type Credential = components["schemas"]["CredentialStatus"];
type Stage = keyof AgentConfig["credential_refs"];

export function CredentialBindingSelect({ stage, provider, value, disabled, change }: {
  stage: Stage;
  provider: Credential["provider"];
  value: string | undefined;
  disabled: boolean;
  change: (id: string | null) => void;
}) {
  const api = useApi();
  const { orgId } = useAuth();
  const [credentials, setCredentials] = useState<Credential[]>([]);
  const load = useCallback(async () => {
    if (!orgId) { setCredentials([]); return; }
    try { setCredentials(await api<Credential[]>(`/orgs/${orgId}/credentials`)); }
    catch { setCredentials([]); }
  }, [api, orgId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { if (!orgId) setCredentials([]); }, [orgId]);
  const eligible = credentials.filter((item) => item.provider === provider && item.status === "stored");
  return <Field>
    <FieldLabel htmlFor={`credential-${stage}`}>{stage} credential</FieldLabel>
    <NativeSelect id={`credential-${stage}`} className="w-full" value={value ?? ""} disabled={disabled} onChange={(event) => change(event.target.value || null)}>
      <option value="">Select an organization credential</option>
      {eligible.map((item) => <option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}
    </NativeSelect>
    <FieldDescription>{eligible.length ? `Bound specifically to ${provider}. A published agent keeps its selected version.` : `Add a stored ${provider} credential in Organization settings first.`}</FieldDescription>
  </Field>;
}

export function bindCredential(config: AgentConfig, stage: Stage, id: string | null): AgentConfig {
  const refs = { ...config.credential_refs };
  if (id) refs[stage] = id;
  else delete refs[stage];
  return { ...config, credential_refs: refs };
}
