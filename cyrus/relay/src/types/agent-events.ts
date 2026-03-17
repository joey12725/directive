/**
 * Standardized NDJSON Event Schema for Agent Communication
 *
 * This schema is consumed by ACPXDispatcher and must remain stable.
 * All agent implementations must emit events in this format.
 */

/**
 * Token usage breakdown
 * Fields are optional to support different provider capabilities
 */
export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
  reasoning_tokens?: number;
}

/**
 * Per-model usage breakdown (for multi-model agents)
 */
export interface ModelUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read?: number;
  cache_creation?: number;
  cost_usd?: number;
}

/**
 * Streaming text chunk event
 * Emitted during response generation
 */
export interface AgentMessageChunkEvent {
  type: 'agent_message_chunk';
  text: string;
  timestamp: string;
}

/**
 * Session completion event
 * Emitted when the agent finishes responding
 * Contains full token usage and cost data
 */
export interface DoneEvent {
  type: 'done';
  timestamp: string;
  model: string;
  provider?: string;
  session_id: string;
  session_key?: string;
  num_turns?: number;
  usage: TokenUsage;
  model_breakdown?: Record<string, ModelUsage>;
  total_cost_usd?: number;
  duration_ms?: number;
  duration_api_ms?: number;
}

/**
 * Relay exit event
 * Emitted when the relay process completes
 */
export interface RelayExitEvent {
  type: 'relay_exit';
  code: number;
  timestamp: string;
  cwd: string;
  agent: string;
}

/**
 * Relay error event
 * Emitted when an error occurs during processing
 */
export interface RelayErrorEvent {
  type: 'relay_error';
  message: string;
  timestamp: string;
  cwd: string;
  agent: string;
  raw?: unknown;
}

/**
 * Union type of all possible NDJSON events
 */
export type AgentEvent =
  | AgentMessageChunkEvent
  | DoneEvent
  | RelayExitEvent
  | RelayErrorEvent;

/**
 * Exec result (non-streaming)
 * Returned from /exec endpoint
 */
export interface ExecResult {
  code: number;
  stdout: string;
  stderr: string;
  output_text: string;
  session_id?: string;
  session_key?: string;
  model?: string;
  provider?: string;
  duration_ms?: number;
  usage?: TokenUsage;
  total_cost_usd?: number;
  raw?: unknown;
}

/**
 * Validation helpers
 */
export const isAgentMessageChunk = (event: unknown): event is AgentMessageChunkEvent => {
  return typeof event === 'object' && event !== null && 'type' in event && event.type === 'agent_message_chunk';
};

export const isDoneEvent = (event: unknown): event is DoneEvent => {
  return typeof event === 'object' && event !== null && 'type' in event && event.type === 'done';
};

export const isRelayExitEvent = (event: unknown): event is RelayExitEvent => {
  return typeof event === 'object' && event !== null && 'type' in event && event.type === 'relay_exit';
};

export const isRelayErrorEvent = (event: unknown): event is RelayErrorEvent => {
  return typeof event === 'object' && event !== null && 'type' in event && event.type === 'relay_error';
};
