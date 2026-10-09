import type { components } from "../../generated/api";

export type ToolContextDelivery =
  components["schemas"]["ToolContextDeliveryResponse"];
export type ClassifierResult =
  components["schemas"]["ClassifierResultResponse"];
export type ClassifierContextDelivery =
  components["schemas"]["ClassifierContextDeliveryResponse"];
export type Interruption = components["schemas"]["InterruptionResponse"];
export type Diagnostic = components["schemas"]["DiagnosticResponse"];

export type RunSummary = {
  id: string;
  channel: "phone" | "browser";
  transport_provider?: string;
  agent_version_id: string;
  contact_id: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  status: string;
  call_outcome?: string | null;
  created_at: string;
  started_at: string | null;
  ended_at: string | null;
};

export type RunDetail = RunSummary & {
  config_hash: string | null;
  resolved_config: Record<string, unknown> | null;
  contact_snapshot: Record<string, unknown> | null;
  call_id: string | null;
  error: string | null;
  termination?: Record<string, unknown> | null;
};

export type Exchange = {
  id: string;
  sequence: number;
  origin: string;
  status: string;
  created_at: string;
  ended_at: string | null;
};

export type Message = {
  id: string;
  exchange_id: string;
  sequence: number;
  role: string;
  content: string;
  interrupted: boolean;
  created_at: string;
  source_at: string | null;
  playback_started_at: string | null;
  playback_ended_at: string | null;
};

export type Span = {
  id: string;
  exchange_id: string | null;
  parent_id: string | null;
  name: string;
  category: string;
  status: string;
  output_state: string;
  interruption_id: string | null;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  provider: string | null;
  model: string | null;
  ttfb_ms: number | null;
  ttfa_ms: number | null;
  ttfat_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  cache_read_input_tokens: number | null;
  cache_creation_input_tokens: number | null;
  reasoning_tokens: number | null;
  audio_seconds: number | null;
  otel_trace_id: string | null;
  otel_span_id: string | null;
  attributes: Record<string, unknown>;
  input: unknown;
  output: unknown;
};

export type Tool = {
  id: string;
  exchange_id: string | null;
  llm_operation_id: string | null;
  function_call_id: string | null;
  binding_key: string;
  status: string;
  interruption_id: string | null;
  arguments: unknown;
  result: unknown;
  started_at: string;
  ended_at: string | null;
  provider_message_id: string | null;
  receipts: components["schemas"]["TimelineTool"]["receipts"];
};

export type ToolResult = {
  id: string;
  tool_invocation_id: string;
  sequence: number;
  payload: unknown;
  is_final: boolean;
  occurred_at: string;
  consumed_at: string | null;
  consumed_exchange_id: string | null;
};

export type FlowVisit = {
  id: string;
  sequence: number;
  node_key: string;
  span_id: string;
  entered_at: string;
  exited_at: string | null;
  triggered_by_tool_id: string | null;
};

export type Timeline = components["schemas"]["TimelineResponse"];

export type Artifact = components["schemas"]["RecordingResponse"];

export type Selection =
  | { kind: "run" }
  | { kind: "prompt" }
  | { kind: "message"; id: string }
  | { kind: "span"; id: string }
  | { kind: "tool"; id: string }
  | { kind: "result"; id: string }
  | { kind: "interruption"; id: string }
  | { kind: "visit"; id: string };
