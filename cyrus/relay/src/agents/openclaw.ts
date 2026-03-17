/**
 * OpenClaw Gateway Runner
 *
 * Uses OpenClaw's native gateway protocol
 * Supports all providers that OpenClaw integrates with
 */

import { AgentRunner, type PromptRequest, dispatchToExec } from './base.js';
import type { AgentEvent, ExecResult, TokenUsage } from '../types/agent-events.js';

// These would be imported from the main relay file
// For now, declare as external dependencies
declare function runOpenClawPrompt(prompt: string, cwd: string): Promise<any>;

export class OpenClawRunner extends AgentRunner {
  readonly name = 'openclaw';

  canHandle(agent: string): boolean {
    return agent.trim().toLowerCase() === 'openclaw';
  }

  async *dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown> {
    try {
      // Execute prompt via OpenClaw gateway
      const result = await runOpenClawPrompt(request.prompt, request.cwd);

      // Emit message chunk if we have output
      if (result.outputText) {
        yield {
          type: 'agent_message_chunk',
          text: result.outputText,
          timestamp: new Date().toISOString(),
        };
      }

      // Build usage object with all available token metrics
      const usage: TokenUsage = {
        input_tokens: result.usage.inputTokens,
        output_tokens: result.usage.outputTokens,
        total_tokens: result.usage.totalTokens,
      };

      // Add cache tokens if available (Anthropic)
      if (result.usage.cacheReadTokens !== undefined) {
        usage.cache_read_input_tokens = result.usage.cacheReadTokens;
      }
      if (result.usage.cacheWriteTokens !== undefined) {
        usage.cache_creation_input_tokens = result.usage.cacheWriteTokens;
      }

      // Add reasoning tokens if available (o1, R1)
      if (result.usage.reasoningTokens !== undefined) {
        usage.reasoning_tokens = result.usage.reasoningTokens;
      }

      // Emit done event
      const doneEvent: AgentEvent = {
        type: 'done',
        timestamp: new Date().toISOString(),
        model: result.model || 'unknown',
        provider: result.provider,
        session_id: result.sessionId || 'unknown',
        session_key: result.sessionKey,
        duration_ms: result.durationMs,
        usage,
        total_cost_usd: result.cost,
      };

      yield doneEvent;

      // Emit relay_exit event
      yield {
        type: 'relay_exit',
        code: 0,
        timestamp: new Date().toISOString(),
        cwd: request.cwd,
        agent: this.name,
      };
    } catch (error) {
      // Emit error event
      yield {
        type: 'relay_error',
        message: error instanceof Error ? error.message : String(error),
        timestamp: new Date().toISOString(),
        cwd: request.cwd,
        agent: this.name,
      };

      // Emit relay_exit with error code
      yield {
        type: 'relay_exit',
        code: 1,
        timestamp: new Date().toISOString(),
        cwd: request.cwd,
        agent: this.name,
      };
    }
  }

  async exec(request: PromptRequest): Promise<ExecResult> {
    return dispatchToExec(this, request);
  }

  async status(cwd: string): Promise<{
    agent: string;
    status: 'available' | 'unavailable';
    stdout?: string;
    stderr?: string;
  }> {
    // OpenClaw status would check gateway availability
    // For now, return a basic implementation
    return {
      agent: this.name,
      status: 'available',
      stdout: 'OpenClaw gateway runner',
    };
  }
}
