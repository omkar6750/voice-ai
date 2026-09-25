// Shape mirrors voice_runtime.contracts.AgentConfig. Preserve untouched keys on every edit.
export type ToolBinding = { tool_id: string; tool_version_id: string };
export type FlowNode = {
  id: string;
  prompt: string;
  transitions: string[];
  tool_bindings: string[];
  entry_actions: string[];
  exit_actions: string[];
  respond_immediately: boolean;
  terminal: boolean;
};
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
    prompt_composition: "node_only" | "global_plus_node";
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
    provider: "groq";
    model: string;
    temperature: number;
    max_tokens: number;
    top_p: number | null;
    reasoning_effort: "none";
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
    summarizer: Record<string, unknown>;
  };
  classifier: Record<string, unknown>;
  pipeline_logs: "inherit" | "enabled" | "disabled";
};
export type AgentVersion = {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  note: string | null;
  config: AgentConfig;
};
export type ProviderCatalog = {
  providers: { provider: string; slots: string[]; models: string[] }[];
};
export type ToolSummary = { id: string; name: string };
export type ToolVersion = {
  id: string;
  version: number;
  status: string;
  config: { name: string; description: string; kind: string };
};
