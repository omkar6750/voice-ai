import type { components } from "@/generated/api";

export type ContactVariablesResponse = components["schemas"]["ContactVariablesResponse"];
export type VariableDescriptor = components["schemas"]["VariableDescriptor"];

type DeepRequired<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly (infer U)[]
    ? DeepRequired<U>[]
    : T extends object
      ? { [K in keyof T]-?: DeepRequired<Exclude<T[K], undefined>> }
      : T;

// The API accepts omitted fields with Pydantic defaults; the editor works on the normalized form.
export type AgentConfig = DeepRequired<components["schemas"]["AgentConfig"]>;
export type ToolBinding = AgentConfig["tool_bindings"][string];
export type FlowNode = AgentConfig["flow"]["nodes"][number];
export type CallbackRole = AgentConfig["callback_scheduling"]["roles"][number];
export type BookablePerson = AgentConfig["callback_scheduling"]["bookable_people"][number];
export type CallbackSchedulingConfig = { enabled: boolean; slot_duration_minutes: number; minimum_notice_minutes: number; roles: CallbackRole[]; bookable_people: BookablePerson[] };
export function normalizeCallbackScheduling(value?: (Omit<Partial<CallbackSchedulingConfig>, "roles" | "bookable_people"> & { roles?: Array<Partial<CallbackRole> & { key: string; label: string }>; bookable_people?: Array<Partial<BookablePerson> & { key: string; name: string }> }) | null): CallbackSchedulingConfig {
  return {
    enabled: value?.enabled ?? false,
    slot_duration_minutes: value?.slot_duration_minutes ?? 15,
    minimum_notice_minutes: value?.minimum_notice_minutes ?? 0,
    roles: (value?.roles ?? []).map((role) => ({ key: role.key, label: role.label, description: role.description ?? "", enabled: role.enabled ?? true })),
    bookable_people: (value?.bookable_people ?? []).map((person) => ({ key: person.key, name: person.name, roles: person.roles ?? [], calendar_integration_id: person.calendar_integration_id ?? "", timezone: person.timezone ?? "UTC", enabled: person.enabled ?? true })),
  };
}
export type CadenceConfig = {
  enabled: boolean;
  node_entries?: string[];
  node_exits?: string[];
  every_n_exchanges?: number | null;
};

export type JevQuestion = {
  type: string;
  instructions: string;
  criteria: Record<string, string>;
};

export type JevClassifierConfig = {
  model: string;
  api_url: string;
  questions: Record<string, JevQuestion>;
};

export type ClassifierConfig = CadenceConfig & {
  classifier_type?: "llm" | "jev";
  llm?: {
    provider?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
    prompt?: string;
    output_fields?: Record<string, string[]>;
    max_output_tokens?: number;
  };
  jev?: JevClassifierConfig & { output_fields?: string[] };
  max_result_chars?: number;
};

export type SummarizerConfig = AgentConfig["context"]["summarizer"];

export type AgentVersion = {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  note: string | null;
  config: AgentConfig;
};
export type ProviderCatalog = components["schemas"]["ProviderCatalogResponse"];
export type ProviderEntry = components["schemas"]["ProviderEntryResponse"];
export type ProviderField = components["schemas"]["ProviderField"];
export type ProviderVoice = components["schemas"]["ProviderVoice"];
export type ToolSummary = { id: string; name: string };
export type ToolVersion = {
  id: string;
  version: number;
  status: string;
  config: { name: string; description: string; kind: string };
};
