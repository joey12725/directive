/**
 * Types for the Session Replay Viewer.
 * Maps to the CyrusSession Django model + parsed NDJSON event_log.
 */

export type SessionStatus = "running" | "completed" | "failed" | "cancelled" | "rate_limited";

export type EventType = "text" | "tool_call" | "thinking" | "error" | "session_started" | "done" | "unknown";

export interface SessionEvent {
  type: EventType | string;
  /** Markdown/plain text content for text events */
  text?: string;
  /** Tool call details */
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  tool_output?: string;
  tool_status?: "success" | "error";
  /** Error details */
  error?: string;
  error_code?: string;
  /** Thinking content */
  content?: string;
  /** Token usage (typically on "done" events) */
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
    cache_read_input_tokens?: number;
    reasoning_tokens?: number;
  };
  /** Session / model identifiers */
  session_id?: string;
  model?: string;
  model_name?: string;
  provider?: string;
  /** Timestamp if present */
  timestamp?: string;
  /** Catch-all for unknown fields */
  [key: string]: unknown;
}

export interface Session {
  id: string;
  agent: string | null;
  agent_name?: string;
  goal: string | null;
  goal_name?: string;
  project: string | null;
  project_name?: string;
  work_item: string | null;
  work_item_name?: string;
  pool: string;
  pool_name?: string;
  acpx_session_id: string;
  started_at: string;
  ended_at: string | null;
  status: SessionStatus;
  event_log: SessionEvent[];
  summary: string;
  outcome: Record<string, unknown>;
  total_tokens: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
  duration_seconds: number;
  model_name: string;
  was_rate_limited: boolean;
  rate_limit_wait_seconds: number;
  langfuse_trace_id: string;
  langfuse_trace_url: string;
  created_at: string;
  updated_at: string;
}
