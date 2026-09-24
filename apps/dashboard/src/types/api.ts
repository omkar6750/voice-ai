/**
 * Strongly typed client DTOs mirroring backend Pydantic models and voice-runtime contracts.
 * Matches:
 * - voice_runtime.contracts (AgentConfig, FlowConfig, Providers, Tools, Knowledge, Cadence)
 * - voice_api.schemas (agent, contact, knowledge, integrations, execution, callbacks)
 */

// ==========================================
// 1. Providers & Runtime Contracts
// ==========================================

export interface LLMConfig {
  provider: "groq" | "google";
  model: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number | null;
  reasoning_effort?: string;
}

export interface STTConfig {
  provider: "sarvam" | "deepgram";
  model: string;
  language?: string;
}

export interface TTSConfig {
  provider: "sarvam" | "cartesia";
  voice: string;
  model?: string;
  language?: string;
  pace?: number;
  speed?: number;
  emotion?: string[];
}

export interface VADConfig {
  provider?: "silero";
  confidence?: number;
  start_secs?: number;
  stop_secs?: number;
  min_volume?: number;
}

export interface AudioConfig {
  sample_rate?: number;
  channels?: number;
  encoding?: string;
  frame_ms?: number;
  frame_size_ms?: number;
}

export interface CallLimits {
  max_duration_secs?: number;
  max_duration_seconds?: number;
  idle_timeout_secs?: number;
  silence_timeout_seconds?: number;
  max_user_interruptions?: number;
  interruptions_enabled?: boolean;
}

// ==========================================
// 2. Cadence & Context
// ==========================================

export interface ClassifierConfig {
  enabled?: boolean;
  node_exits?: string[];
  model?: LLMConfig;
  prompt?: string;
  confidence_threshold?: number;
  consecutive_verdicts?: number;
  answer_signals?: string[];
  topic_signals?: string[];
  keywords?: string[];
}

export interface SummarizerConfig {
  enabled?: boolean;
  model?: LLMConfig;
  prompt?: string;
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
}

export interface ContextConfig {
  prune_node_ids?: string[];
  remove_transition_tool_pairs?: boolean;
  summarizer?: SummarizerConfig;
}

export interface LanguageConfig {
  default_language: string;
  supported_languages: string[];
  follow_caller_language?: boolean;
  persist_requested_language?: boolean;
}

// ==========================================
// 3. Flow & Agent Graph Contracts
// ==========================================

export interface FlowNodeConfig {
  id: string;
  prompt: string;
  transitions: string[];
  tool_bindings?: string[];
  entry_actions?: string[];
  exit_actions?: string[];
  respond_immediately?: boolean;
  terminal?: boolean;
}

export interface FlowConfig {
  initial_node: string;
  nodes: FlowNodeConfig[];
  prompt_composition?: "node_only" | "global_plus_node";
}

export interface AgentConfig {
  name?: string;
  persona?: string;
  system_prompt: string;
  greeting?: string;
  contact_variables?: string[];
  language?: LanguageConfig;
  flow: FlowConfig;
  tool_bindings?: Record<string, unknown>;
  background_hooks?: string[];
  knowledge_base_ids?: string[];
  retrieval?: RetrievalConfig;
  stt?: STTConfig;
  llm?: LLMConfig;
  tts?: TTSConfig;
  vad?: VADConfig;
  audio?: AudioConfig;
  call_limits?: CallLimits;
  context?: ContextConfig;
  classifier?: ClassifierConfig;
  pipeline_logs?: "inherit" | "enabled" | "disabled";
}

export interface AgentSummary {
  id: string;
  name: string;
  active_version_id: string | null;
}

export interface AgentVersionSummary {
  id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  config: AgentConfig;
  note?: string | null;
  published_at?: string | null;
}

export interface CreateAgentBody {
  name: string;
  config: AgentConfig;
}

export interface UpdateAgentVersionBody {
  revision: number;
  config: AgentConfig;
  note?: string | null;
}

export interface ExpectedRevisionBody {
  revision: number;
}

export interface ActivateAgentBody {
  version_id: string;
}

// ==========================================
// 4. Contacts
// ==========================================

export interface ContactItem {
  id: string;
  name: string;
  phone_number: string;
  timezone?: string | null;
  business?: string | null;
  source?: string | null;
  language?: string | null;
}

export interface ContactBody {
  name: string;
  phone_number: string;
  timezone?: string | null;
  business?: string | null;
  source?: string | null;
  language?: string | null;
}

// ==========================================
// 5. Integrations & WhatsApp
// ==========================================

export interface WhatsAppConfig {
  phone_number_id: string;
  waba_id: string;
  api_version: string;
}

export interface IntegrationConnection {
  id: string;
  label: string;
  provider: "whatsapp";
  config: WhatsAppConfig;
  enabled: boolean;
  secret_names: string[];
}

export interface CreateConnectionBody {
  label: string;
  provider: "whatsapp";
  config: WhatsAppConfig;
  enabled?: boolean;
}

export interface SecretBody {
  value: string;
}

export interface WhatsAppTemplateItem {
  name: string;
  language: string;
  status: string;
  category?: string;
  components?: Array<{
    type: string;
    text?: string;
    format?: string;
    example?: Record<string, unknown>;
  }>;
}

// ==========================================
// 6. Knowledge Bases & RAG
// ==========================================

export interface KnowledgeConfig {
  chunk_size: number;
  chunk_overlap: number;
  markdown_aware: boolean;
  supported_sources: string[];
  extraction_max_chars?: number;
}

export interface RetrievalConfig {
  top_k?: number;
  context_budget?: number;
  timeout_seconds?: number;
  vector_weight?: number;
  keyword_weight?: number;
  rerank_enabled?: boolean;
}

export interface KnowledgeBaseItem {
  id: string;
  name: string;
  config: KnowledgeConfig;
}

export interface SourceItem {
  id: string;
  title: string;
  kind: "paste" | "txt" | "md" | "pdf";
  status: "pending" | "building" | "ready" | "failed";
  error?: string | null;
}

export interface SourceCreateBody {
  title: string;
  content: string;
  kind: "paste" | "txt" | "md" | "pdf";
}

export interface SearchRequest {
  query: string;
  retrieval?: RetrievalConfig;
}

export interface SearchHit {
  chunk_id: string;
  source_id: string;
  title: string;
  source_path?: string | null;
  ordinal: number;
  content: string;
  score: number;
  score_type?: string;
  metadata?: Record<string, unknown>;
}

// ==========================================
// 7. Tools & Runtime Registry
// ==========================================

export interface ToolItem {
  id: string;
  name: string;
}

export interface ToolVersionItem {
  id: string;
  tool_id: string;
  version: number;
  revision: number;
  status: "draft" | "published";
  config: Record<string, unknown>;
  published_at?: string | null;
}

// ==========================================
// 8. Callbacks & Telephony Endpoints
// ==========================================

export interface CallbackItem {
  id: string;
  request_key: string;
  contact_id: string;
  agent_version_id: string;
  due_at: string;
  timezone: string;
  original_phrase: string;
  status: "scheduled" | "dispatched" | "cancelled" | "failed";
  call_id?: string | null;
  automatic_attempts: number;
}

export interface RuntimeEndpointItem {
  id: string;
  name: string;
  config: {
    at_port: string;
    audio_port: string;
    baudrate: number;
    pcm_rate: number;
  };
  created_at: string;
}

export interface EndpointCreateBody {
  name: string;
  config: {
    at_port: string;
    audio_port: string;
    baudrate: number;
    pcm_rate: number;
  };
}

// ==========================================
// 9. Settings
// ==========================================

export interface WorkspaceSettingsConfig {
  audio_recording_retention_days?: number;
  pipeline_log_retention_days?: number;
  callback_dispatch_window_minutes?: number;
  sim7600_default_at_port?: string;
  sim7600_default_audio_port?: string;
}
