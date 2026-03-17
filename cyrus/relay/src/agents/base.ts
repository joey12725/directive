/**
 * Abstract Agent Runner Interface
 *
 * All agent implementations must implement this interface to ensure:
 * 1. Consistent API regardless of underlying provider
 * 2. Standardized event format for ACPXDispatcher
 * 3. Easy extensibility for new agents
 *
 * The relay routes requests to concrete implementations via AgentFactory.
 */

import type { AgentEvent, ExecResult } from '../types/agent-events.js';

/**
 * Common prompt request parameters
 */
export interface PromptRequest {
  prompt: string;
  cwd: string;
  session_name?: string;
  approve_all?: boolean;
}

/**
 * Abstract base class for all agent runners
 *
 * Concrete implementations:
 * - ClaudeCodeRunner (native CLI)
 * - OpenClawRunner (gateway)
 * - ACPXRunner (generic ACPX wrapper)
 * - CodexRunner (native CLI or ACPX)
 * - GeminiRunner (native CLI or ACPX)
 */
export abstract class AgentRunner {
  /**
   * Agent identifier (e.g., 'claude', 'openclaw', 'codex')
   */
  abstract readonly name: string;

  /**
   * Check if this runner can handle the given agent name
   */
  abstract canHandle(agent: string): boolean;

  /**
   * Execute a prompt and stream NDJSON events
   *
   * This is the primary method for agentic workflows.
   * Must emit events in standardized format:
   * 1. agent_message_chunk (0+ times)
   * 2. done (exactly once)
   * 3. relay_exit (exactly once)
   *
   * @param request - Prompt request parameters
   * @returns AsyncGenerator yielding AgentEvent objects
   */
  abstract dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown>;

  /**
   * Execute a prompt and return final result (non-streaming)
   *
   * This is a convenience method for simple request/response.
   * Internally may call dispatch() and collect events.
   *
   * @param request - Prompt request parameters
   * @returns ExecResult with output and usage data
   */
  abstract exec(request: PromptRequest): Promise<ExecResult>;

  /**
   * Check if agent is available/healthy
   *
   * Used by /agents endpoint to report status.
   *
   * @param cwd - Working directory for status check
   * @returns Status object with agent health
   */
  abstract status(cwd: string): Promise<{
    agent: string;
    status: 'available' | 'unavailable';
    stdout?: string;
    stderr?: string;
  }>;
}

/**
 * Helper to convert dispatch() stream to exec() result
 *
 * This allows exec() implementations to reuse dispatch() logic
 * while providing a simpler non-streaming API.
 */
export async function dispatchToExec(
  runner: AgentRunner,
  request: PromptRequest
): Promise<ExecResult> {
  let outputText = '';
  let sessionId: string | undefined;
  let sessionKey: string | undefined;
  let model: string | undefined;
  let provider: string | undefined;
  let durationMs: number | undefined;
  let usage: any;
  let totalCostUsd: number | undefined;
  let exitCode = 0;

  for await (const event of runner.dispatch(request)) {
    if (event.type === 'agent_message_chunk') {
      outputText += event.text;
    } else if (event.type === 'done') {
      sessionId = event.session_id;
      sessionKey = event.session_key;
      model = event.model;
      provider = event.provider;
      durationMs = event.duration_ms;
      usage = event.usage;
      totalCostUsd = event.total_cost_usd;
    } else if (event.type === 'relay_exit') {
      exitCode = event.code;
    }
  }

  return {
    code: exitCode,
    stdout: JSON.stringify({ outputText, usage }),
    stderr: '',
    output_text: outputText,
    session_id: sessionId,
    session_key: sessionKey,
    model,
    provider,
    duration_ms: durationMs,
    usage,
    total_cost_usd: totalCostUsd,
  };
}
