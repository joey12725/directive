/**
 * Claude Code Native Runner
 *
 * Uses Claude Code's native CLI with --output-format stream-json
 * Bypasses ACPX to get full features (cache tokens, multi-model, cost)
 */

import { spawn } from 'node:child_process';
import { AgentRunner, type PromptRequest, dispatchToExec } from './base.js';
import type {
  AgentEvent,
  ExecResult,
  TokenUsage,
  ModelUsage,
} from '../types/agent-events.js';

const claudeBinary = process.env.CYRUS_CLAUDE_BINARY
  || (process.platform === 'win32' ? 'claude.exe' : 'claude');

export class ClaudeCodeRunner extends AgentRunner {
  readonly name = 'claude';

  canHandle(agent: string): boolean {
    return agent.trim().toLowerCase() === 'claude';
  }

  async *dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown> {
    const proc = spawn(
      claudeBinary,
      ['--print', '--output-format', 'stream-json', '--verbose', request.prompt],
      {
        cwd: request.cwd,
        env: process.env,
        shell: false,
        stdio: ['ignore', 'pipe', 'pipe'],
      }
    );

    let buffer = '';
    let claudeModel = 'claude-sonnet-4-5-20250929';
    let sessionId: string | undefined;
    let totalUsage: any = {};
    let responseText = '';

    // Parse stdout stream
    const stdoutPromise = new Promise<void>((resolve) => {
      proc.stdout.on('data', (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const event = JSON.parse(line);

            // Transform Claude events to standardized format
            if (event.type === 'system' && event.subtype === 'init') {
              sessionId = event.session_id;
              claudeModel = event.model;
            } else if (event.type === 'assistant') {
              // Extract text from assistant message
              const text = event.message?.content?.find((c: any) => c.type === 'text')?.text || '';
              if (text) {
                responseText += text;
                // Emit agent_message_chunk event
                const chunkEvent: AgentEvent = {
                  type: 'agent_message_chunk',
                  text,
                  timestamp: new Date().toISOString(),
                };
                proc.emit('event', chunkEvent);
              }
              // Track usage
              if (event.message?.usage) {
                totalUsage = event.message.usage;
              }
            } else if (event.type === 'result') {
              // Send done event with full usage
              const usage = event.usage || totalUsage;

              // Parse modelUsage to get actual token counts across ALL models
              let totalInputTokens = 0;
              let totalOutputTokens = 0;
              let totalCacheRead = usage.cache_read_input_tokens || 0;
              let totalCacheCreation = usage.cache_creation_input_tokens || 0;
              const modelBreakdown: Record<string, ModelUsage> = {};

              if (event.modelUsage) {
                // Aggregate usage across all models (Sonnet for main, Haiku for tools, etc.)
                for (const [modelName, modelStats] of Object.entries(event.modelUsage)) {
                  const stats = modelStats as any;
                  totalInputTokens += stats.inputTokens || 0;
                  totalOutputTokens += stats.outputTokens || 0;
                  totalCacheRead += stats.cacheReadInputTokens || 0;
                  totalCacheCreation += stats.cacheCreationInputTokens || 0;

                  modelBreakdown[modelName] = {
                    input_tokens: stats.inputTokens || 0,
                    output_tokens: stats.outputTokens || 0,
                    cache_read: stats.cacheReadInputTokens || 0,
                    cache_creation: stats.cacheCreationInputTokens || 0,
                    cost_usd: stats.costUSD || 0,
                  };
                }
              } else {
                // Fallback to top-level usage if modelUsage not available
                totalInputTokens = usage.input_tokens || 0;
                totalOutputTokens = usage.output_tokens || 0;
              }

              const tokenUsage: TokenUsage = {
                input_tokens: totalInputTokens,
                output_tokens: totalOutputTokens,
                total_tokens: totalInputTokens + totalOutputTokens,
                cache_read_input_tokens: totalCacheRead,
                cache_creation_input_tokens: totalCacheCreation,
              };

              const doneEvent: AgentEvent = {
                type: 'done',
                timestamp: new Date().toISOString(),
                model: claudeModel,
                session_id: sessionId || 'unknown',
                num_turns: event.num_turns || 1,
                usage: tokenUsage,
                model_breakdown: Object.keys(modelBreakdown).length > 0 ? modelBreakdown : undefined,
                total_cost_usd: event.total_cost_usd,
                duration_ms: event.duration_ms,
                duration_api_ms: event.duration_api_ms,
              };
              proc.emit('event', doneEvent);
            }
          } catch (error) {
            // Skip unparseable lines
          }
        }
      });

      proc.stdout.on('end', resolve);
    });

    // Collect events and yield them
    const events: AgentEvent[] = [];
    proc.on('event', (event: AgentEvent) => {
      events.push(event);
    });

    // Wait for process completion
    const exitCode = await new Promise<number>((resolve) => {
      proc.on('close', (code) => resolve(code ?? 1));
      proc.on('error', () => resolve(1));
    });

    await stdoutPromise;

    // Yield all collected events
    for (const event of events) {
      yield event;
    }

    // Emit relay_exit event
    yield {
      type: 'relay_exit',
      code: exitCode,
      timestamp: new Date().toISOString(),
      cwd: request.cwd,
      agent: this.name,
    };
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
    try {
      const proc = spawn(claudeBinary, ['--version'], {
        cwd,
        shell: false,
        stdio: ['ignore', 'pipe', 'pipe'],
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (chunk) => {
        stdout += chunk.toString();
      });

      proc.stderr.on('data', (chunk) => {
        stderr += chunk.toString();
      });

      const code = await new Promise<number>((resolve) => {
        proc.on('close', (c) => resolve(c ?? 1));
      });

      return {
        agent: this.name,
        status: code === 0 ? 'available' : 'unavailable',
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      };
    } catch (error) {
      return {
        agent: this.name,
        status: 'unavailable',
        stderr: error instanceof Error ? error.message : String(error),
      };
    }
  }
}
