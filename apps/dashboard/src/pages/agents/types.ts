import type { components } from "@/generated/api";

export type ContactVariablesResponse = components["schemas"]["ContactVariablesResponse"];
export type VariableDescriptor = components["schemas"]["VariableDescriptor"];

// Shape mirrors voice_runtime.contracts.AgentConfig. Preserve untouched keys on every edit.
export type ToolBinding = { tool_id: string; tool_version_id: string };
export type FlowNode = {
  id: string;
  prompt: string;
  role_prompt?: string | null;
  context_strategy?: "append" | "reset";
  transitions: string[];
  tool_bindings: string[];
  entry_actions: string[];
  exit_actions: string[];
  respond_immediately: boolean;
  terminal: boolean;
};
export type CallbackRole = { key: string; label: string; description: string; enabled: boolean };
export type BookablePerson = { key: string; name: string; roles: string[]; calendar_integration_id: string; timezone: string; enabled: boolean };
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
export type AgentConfig = {
  name: string;
  persona: string;
  system_prompt: string;
  greeting: string;
  contact_variables: string[];
  language: {
    default_language: string;
    supported_languages: string[];
    follow_caller_language: boolean;
    persist_requested_language: boolean;
  };
  flow: {
    initial_node: string;
    nodes: FlowNode[];
    /** @deprecated retained for old saved versions. */
    prompt_composition?: "node_only" | "global_plus_node";
  };
  tool_bindings: Record<string, ToolBinding>;
  background_hooks: string[];
  knowledge_base_ids: string[];
  retrieval: {
    top_k: number;
    keyword_weight: number;
    vector_weight: number;
    rrf_k: number;
    min_vector_similarity: number | null;
    min_keyword_score: number | null;
    result_budget_tokens: number;
    timeout_secs: number;
    reranking_enabled: false;
    wait: { mode: string; acknowledgement: string | null };
  };
  stt: { provider: "sarvam"; model: "saaras:v3" };
  llm: {
    provider: "groq" | "gemini";
    model: string;
    temperature: number;
    max_tokens: number;
    top_p: number | null;
    reasoning_effort: "none" | "provider_default";
  };
  tts: {
    provider: "sarvam" | "cartesia";
    model: string;
    voice: string;
    language: string;
    pace: number;
  };
  audio: {
    sample_rate: 8000 | 16000;
    channels: 1;
    encoding: "pcm_s16le";
    frame_ms: 20;
  };
  vad: {
    confidence: number;
    start_secs: number;
    stop_secs: number;
    min_volume: number;
  };
  call_limits: {
    max_duration_secs: number;
    idle_timeout_secs: number;
    interruptions_enabled: boolean;
  };
  context: {
    prune_node_ids: string[];
    remove_transition_tool_pairs: boolean;
    summarizer: SummarizerConfig;
  };
  classifier: ClassifierConfig;
  callback_scheduling: {
    enabled: boolean;
    slot_duration_minutes: number;
    minimum_notice_minutes: number;
    roles: { key: string; label: string; description: string }[];
    bookable_people: { key: string; name: string; roles: string[]; calendar_integration_id: string; timezone: string; enabled: boolean }[];
  };
  pipeline_logs: "inherit" | "enabled" | "disabled";
};

export type CadenceConfig = {
  enabled: boolean;
  node_entries?: string[];
  node_exits?: string[];
  every_n_exchanges?: number | null;
  interval_secs?: number | null;
  explicit_requests?: boolean;
  on_finalization?: boolean;
  cooldown_secs?: number;
  max_attempts?: number;
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
  model?: {
    provider?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
  };
  prompt?: string;
  jev?: JevClassifierConfig;
  answer_signals?: string[];
  topic_signals?: string[];
  keywords?: string[];
  confidence_threshold?: number;
  consecutive_verdicts?: number;
};

export type SummarizerConfig = CadenceConfig & {
  model?: {
    provider?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
  };
  prompt?: string;
  answer_signals?: string[];
  topic_signals?: string[];
  keywords?: string[];
  unsummarized_messages?: number;
  unsummarized_exchanges?: number | null;
  token_threshold?: number | null;
  context_window_tokens?: number;
  compaction_threshold?: number;
  hard_ceiling?: number;
  target_ratio?: number;
  output_budget_tokens?: number;
  preserve_opening_messages?: number;
  preserve_recent_messages?: number;
};

export type AgentVersion = {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  note: string | null;
  config: AgentConfig;
};
export type ProviderVoice = { id: string; name: string; gender?: string };
export type ProviderEntry = {
  provider: string;
  slots: string[];
  models: string[];
  models_by_slot?: Record<string, string[]>;
  voices?: ProviderVoice[];
  languages?: string[];
  status?: string;
  checked_at?: string | null;
};
export type ProviderCatalog = {
  providers: ProviderEntry[];
};
export type ToolSummary = { id: string; name: string };
export type ToolVersion = {
  id: string;
  version: number;
  status: string;
  config: { name: string; description: string; kind: string };
};
