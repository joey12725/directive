/**
 * Gemini CLI Native Runner
 *
 * Uses Gemini CLI's native CLI with --output-format stream-json
 * Supports full compute tracking (tokens, model, cost)
 */

import { spawn } from 'node:child_process';
import path from 'node:path';
import os from 'node:os';
import { AgentRunner, type PromptRequest, dispatchToExec } from './base.js';
import type {
  AgentEvent,
  ExecResult,
  TokenUsage,
} from '../types/agent-events.js';

// On Windows, spawn node directly to avoid cmd.exe quoting issues
const geminiBinary = process.platform === 'win32'
  ? 'node'
  : 'gemini';
const geminiArgs = process.platform === 'win32'
  ? [
      '--no-warnings=DEP0040',
      path.join(
        os.homedir(),
        'AppData',
        'Roaming',
        'npm',
        'node_modules',
        '@google',
        'gemini-cli',
        'dist',
        'index.js'
      ),
    ]
  : [];  // On Unix, "gemini" is the wrapper script

export class GeminiRunner extends AgentRunner {
  readonly name = 'gemini';

  canHandle(agent: string): boolean {
    const normalized = agent.trim().toLowerCase();
    return normalized === 'gemini' || normalized === 'gemini-cli';
  }

  async *dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown> {
    const proc = spawn(
      geminiBinary,
      [...geminiArgs, '--prompt', request.prompt, '--output-format', 'stream-json', '--yolo'],
      {
        cwd: request.cwd,
        env: process.env,
        shell: false,
        stdio: ['ignore', 'pipe', 'pipe'],
      }
    );

    let buffer = '';
    let geminiModel = 'unknown';
    let sessionId: string | undefined;
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

            // Transform Gemini events to standardized format
            if (event.type === 'init') {
              sessionId = event.session_id;
              geminiModel = event.model;
            } else if (event.type === 'message' && event.role === 'assistant') {
              const text = event.content || '';
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
            } else if (event.type === 'result') {
              // Send done event with full usage
              const stats = event.stats || {};
              
              const tokenUsage: TokenUsage = {
                input_tokens: stats.input_tokens || 0,
                output_tokens: stats.output_tokens || 0,
                total_tokens: stats.total_tokens || (stats.input_tokens + stats.output_tokens) || 0,
                cache_read_input_tokens: stats.cached || 0,
              };

              const doneEvent: AgentEvent = {
                type: 'done',
                timestamp: new Date().toISOString(),
                model: geminiModel,
                session_id: sessionId || 'unknown',
                usage: tokenUsage,
                duration_ms: stats.duration_ms,
              };
              proc.emit('event', doneEvent);
            }
          } catch (error) {
            // Skip unparseable lines
            // console.error('Failed to parse Gemini output line:', line, error);
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
      const proc = spawn(geminiBinary, [...geminiArgs, '--version'], {
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
