/**
 * Strongly typed client DTOs mirroring backend Pydantic models and voice-runtime contracts.
 * Matches:
 * - voice_runtime.contracts (AgentConfig, FlowConfig, Providers, Tools, Knowledge)
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
  top_p?: number;
}

export interface STTConfig {
  provider: "deepgram";
  model: string;
  language: string;
}

export interface TTSConfig {
  provider: "cartesia";
  voice: string;
  model?: string;
  speed?: number;
  emotion?: string[];
}

export interface VADConfig {
  provider: "silero";
  confidence?: number;
  start_secs?: number;
  stop_secs?: number;
  min_volume?: number;
}

export interface AudioConfig {
  sample_rate?: number;
  channels?: number;
  frame_size_ms?: number;
}

export interface CallLimits {
  max_duration_seconds?: number;
  silence_timeout_seconds?: number;
  max_user_interruptions?: number;
}

// ==========================================
// 2. Flow & Agent Graph Contracts
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
  system_prompt: string;
  flow: FlowConfig;
  llm?: LLMConfig;
  stt?: STTConfig;
  tts?: TTSConfig;
  vad?: VADConfig;
  audio?: AudioConfig;
  call_limits?: CallLimits;
  tool_bindings?: Record<string, { tool_version_id: string; config?: Record<string, unknown> }>;
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
// 3. Contacts
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
// 4. Integrations & WhatsApp
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
// 5. Knowledge Bases & RAG
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
// 6. Tools & Runtime Registry
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
// 7. Callbacks & Telephony Endpoints
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
// 8. Settings
// ==========================================

export interface WorkspaceSettingsConfig {
  audio_recording_retention_days?: number;
  pipeline_log_retention_days?: number;
  callback_dispatch_window_minutes?: number;
  sim7600_default_at_port?: string;
  sim7600_default_audio_port?: string;
}
