/**
 * TEMPLATE: Agent Runner Implementation
 *
 * Copy this file and replace TEMPLATE with your agent name (e.g., Codex, Gemini)
 * Follow the pattern to ensure consistency and compatibility.
 */

import { spawn } from 'node:child_process';
import { AgentRunner, type PromptRequest, dispatchToExec } from './base.js';
import type { AgentEvent, ExecResult, TokenUsage } from '../types/agent-events.js';

/**
 * Configuration
 * Adjust binary path, command format, etc.
 */
const AGENT_BINARY = 'your-agent-cli';  // e.g., 'codex', 'gemini-cli'
const AGENT_NAME = 'template';          // e.g., 'codex', 'gemini'

export class TemplateRunner extends AgentRunner {
  readonly name = AGENT_NAME;

  /**
   * Check if this runner handles the agent
   * Can match multiple names if needed (e.g., 'codex' and 'openai-codex')
   */
  canHandle(agent: string): boolean {
    const normalized = agent.trim().toLowerCase();
    return normalized === AGENT_NAME || normalized === `${AGENT_NAME}-alias`;
  }

  /**
   * Main dispatch method - streams NDJSON events
   *
   * REQUIRED EVENTS:
   * 1. agent_message_chunk (0+ times) - streaming text
   * 2. done (exactly once) - final usage/cost
   * 3. relay_exit (exactly once) - completion status
   *
   * OPTIONAL EVENTS:
   * - relay_error (on errors)
   */
  async *dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown> {
    // Step 1: Spawn the agent process
    const proc = spawn(
      AGENT_BINARY,
      [
        '--output-format', 'json',  // Adjust based on your CLI
        '--prompt', request.prompt,
        // Add other flags as needed
      ],
      {
        cwd: request.cwd,
        env: process.env,
        shell: false,
        stdio: ['ignore', 'pipe', 'pipe'],
      }
    );

    let responseText = '';
    let sessionId = 'unknown';
    let model = 'unknown';
    let usage: TokenUsage = {
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
    };

    // Step 2: Parse stdout and transform to standard events
    const stdoutPromise = new Promise<void>((resolve) => {
      let buffer = '';

      proc.stdout.on('data', (chunk) => {
        buffer += chunk.toString();

        // Parse NDJSON or JSON based on your CLI format
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const data = JSON.parse(line);

            // Transform to standard events
            // ADJUST THIS BASED ON YOUR CLI'S OUTPUT FORMAT
            if (data.type === 'text' || data.delta) {
              const text = data.text || data.delta;
              responseText += text;

              // Emit streaming chunk
              const chunkEvent: AgentEvent = {
                type: 'agent_message_chunk',
                text,
                timestamp: new Date().toISOString(),
              };
              proc.emit('event', chunkEvent);
            }

            if (data.type === 'usage' || data.usage) {
              // Extract usage data
              const usageData = data.usage || data;
              usage = {
                input_tokens: usageData.input_tokens || usageData.promptTokens || 0,
                output_tokens: usageData.output_tokens || usageData.completionTokens || 0,
                total_tokens: usageData.total_tokens || usageData.totalTokens || 0,
              };

              // Add optional fields if available
              if (usageData.cache_read_tokens) {
                usage.cache_read_input_tokens = usageData.cache_read_tokens;
              }
              if (usageData.cache_creation_tokens) {
                usage.cache_creation_input_tokens = usageData.cache_creation_tokens;
              }
              if (usageData.reasoning_tokens) {
                usage.reasoning_tokens = usageData.reasoning_tokens;
              }
            }

            if (data.type === 'metadata' || data.model) {
              model = data.model || data.modelName || 'unknown';
              sessionId = data.session_id || data.sessionId || 'unknown';
            }
          } catch (error) {
            // Skip unparseable lines
          }
        }
      });

      proc.stdout.on('end', resolve);
    });

    // Step 3: Collect events
    const events: AgentEvent[] = [];
    proc.on('event', (event: AgentEvent) => {
      events.push(event);
    });

    // Step 4: Wait for completion
    const exitCode = await new Promise<number>((resolve) => {
      proc.on('close', (code) => resolve(code ?? 1));
      proc.on('error', () => resolve(1));
    });

    await stdoutPromise;

    // Step 5: Yield all collected events
    for (const event of events) {
      yield event;
    }

    // Step 6: Emit done event if not already emitted
    const hasDoneEvent = events.some(e => e.type === 'done');
    if (!hasDoneEvent) {
      yield {
        type: 'done',
        timestamp: new Date().toISOString(),
        model,
        session_id: sessionId,
        usage,
        // Add total_cost_usd if your CLI provides it
      };
    }

    // Step 7: Emit relay_exit event
    yield {
      type: 'relay_exit',
      code: exitCode,
      timestamp: new Date().toISOString(),
      cwd: request.cwd,
      agent: this.name,
    };
  }

  /**
   * Exec method - non-streaming
   *
   * Default implementation uses dispatch() and collects results.
   * Override if your CLI has a simpler non-streaming mode.
   */
  async exec(request: PromptRequest): Promise<ExecResult> {
    return dispatchToExec(this, request);
  }

  /**
   * Status check - verify agent is available
   *
   * Used by /agents endpoint to report health.
   */
  async status(cwd: string): Promise<{
    agent: string;
    status: 'available' | 'unavailable';
    stdout?: string;
    stderr?: string;
  }> {
    try {
      const proc = spawn(AGENT_BINARY, ['--version'], {
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

/**
 * CHECKLIST FOR NEW AGENT:
 *
 * 1. Replace TEMPLATE with your agent name throughout
 * 2. Update AGENT_BINARY constant
 * 3. Update AGENT_NAME constant
 * 4. Implement canHandle() logic
 * 5. Adjust spawn() command and flags
 * 6. Parse your CLI's output format in dispatch()
 * 7. Map to standard event format:
 *    - text → agent_message_chunk
 *    - usage → done.usage
 *    - completion → done + relay_exit
 * 8. Test with simple prompt
 * 9. Register in factory (see agents/index.ts)
 * 10. Update relay endpoint to use factory
 *
 * VALIDATION:
 * - Run: curl -X POST http://localhost:7420/dispatch -d '{"agent":"your-agent","prompt":"test"}'
 * - Verify NDJSON output has: agent_message_chunk, done, relay_exit
 * - Verify usage fields are populated
 * - Verify ACPXDispatcher can parse events
 */
