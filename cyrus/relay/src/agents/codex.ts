import { spawn } from "node:child_process";
import { AgentRunner, type PromptRequest, dispatchToExec } from "./base.js";
import type { AgentEvent, ExecResult, TokenUsage } from "../types/agent-events.js";

export const codexBinary = process.platform === "win32" ? "codex.cmd" : "codex";

type CodexUsagePayload = {
  input_tokens?: unknown;
  cached_input_tokens?: unknown;
  output_tokens?: unknown;
  reasoning_tokens?: unknown;
  reasoning_output_tokens?: unknown;
};

type CodexEventState = {
  readonly startedAt: number;
  sessionId?: string;
  model: string;
};

const coerceNumber = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const quoteWindowsArg = (value: string): string => {
  if (!/[\s"]/u.test(value)) {
    return value;
  }

  let quoted = '"';
  let backslashes = 0;

  for (const char of value) {
    if (char === "\\") {
      backslashes += 1;
      continue;
    }

    if (char === '"') {
      quoted += "\\".repeat(backslashes * 2 + 1);
      quoted += char;
      backslashes = 0;
      continue;
    }

    quoted += "\\".repeat(backslashes);
    quoted += char;
    backslashes = 0;
  }

  quoted += "\\".repeat(backslashes * 2);
  quoted += '"';
  return quoted;
};

const buildCodexSpawnTarget = (command: string[]) => {
  if (process.platform !== "win32") {
    return {
      file: command[0],
      args: command.slice(1),
    };
  }

  return {
    file: "cmd.exe",
    args: ["/d", "/s", "/c", command.map(quoteWindowsArg).join(" ")],
  };
};

export const buildCodexCommand = (request: PromptRequest): string[] => {
  const command = ["exec", "--json", "--skip-git-repo-check"];

  if (request.approve_all ?? true) {
    command.push("--dangerously-bypass-approvals-and-sandbox");
  } else {
    command.push("--sandbox", "workspace-write", "-a", "never");
  }

  command.push("-");
  return command;
};

export const buildCodexStatusCommand = (): string[] => ["--version"];

export const normalizeCodexUsage = (usage: CodexUsagePayload | undefined): TokenUsage => {
  const inputTokens = coerceNumber(usage?.input_tokens);
  const outputTokens = coerceNumber(usage?.output_tokens);
  const cacheReadTokens = coerceNumber(usage?.cached_input_tokens);
  const reasoningTokens = coerceNumber(usage?.reasoning_tokens ?? usage?.reasoning_output_tokens);

  return {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    total_tokens: inputTokens + outputTokens,
    cache_read_input_tokens: cacheReadTokens,
    reasoning_tokens: reasoningTokens > 0 ? reasoningTokens : undefined,
  };
};

export const parseCodexEvent = (rawEvent: unknown, state: CodexEventState): AgentEvent[] => {
  if (!rawEvent || typeof rawEvent !== "object") {
    return [];
  }

  const event = rawEvent as Record<string, unknown>;
  const timestamp = new Date().toISOString();

  if (event.type === "thread.started") {
    const threadId = event.thread_id;
    if (typeof threadId === "string" && threadId.length > 0) {
      state.sessionId = threadId;
    }
    return [];
  }

  if (event.type === "item.completed") {
    const item = event.item;
    if (!item || typeof item !== "object") {
      return [];
    }

    const completedItem = item as Record<string, unknown>;
    if (completedItem.type !== "agent_message") {
      return [];
    }

    const text = completedItem.text;
    if (typeof text !== "string" || text.length === 0) {
      return [];
    }

    return [
      {
        type: "agent_message_chunk",
        text,
        timestamp,
      },
    ];
  }

  if (event.type === "turn.completed") {
    const usage = normalizeCodexUsage(event.usage as CodexUsagePayload | undefined);
    const model = typeof event.model === "string" && event.model.length > 0 ? event.model : state.model;
    state.model = model;

    return [
      {
        type: "done",
        timestamp,
        model,
        provider: "openai",
        session_id: state.sessionId ?? "unknown",
        usage,
        duration_ms: Date.now() - state.startedAt,
      },
    ];
  }

  return [];
};

export class CodexRunner extends AgentRunner {
  readonly name = "codex";

  canHandle(agent: string): boolean {
    const normalized = agent.trim().toLowerCase();
    return normalized === "codex" || normalized === "codex-cli";
  }

  async *dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown> {
    const target = buildCodexSpawnTarget([codexBinary, ...buildCodexCommand(request)]);
    const proc = spawn(target.file, target.args, {
      cwd: request.cwd,
      env: process.env,
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
    });

    proc.stdin.end(request.prompt);

    let buffer = "";
    let stderr = "";
    const state: CodexEventState = {
      startedAt: Date.now(),
      model: process.env.CYRUS_CODEX_MODEL ?? "codex",
    };

    const stdoutPromise = new Promise<void>((resolve) => {
      proc.stdout.on("data", (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) {
            continue;
          }

          try {
            const parsed = JSON.parse(line);
            for (const event of parseCodexEvent(parsed, state)) {
              proc.emit("event", event);
            }
          } catch {
            proc.emit("event", {
              type: "relay_error",
              message: `Failed to parse Codex event: ${line}`,
              timestamp: new Date().toISOString(),
              cwd: request.cwd,
              agent: this.name,
              raw: line,
            } satisfies AgentEvent);
          }
        }
      });

      proc.stdout.on("end", resolve);
    });

    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    const events: AgentEvent[] = [];
    proc.on("event", (event: AgentEvent) => {
      events.push(event);
    });

    const exitCode = await new Promise<number>((resolve) => {
      proc.on("close", (code) => resolve(code ?? 1));
      proc.on("error", () => resolve(1));
    });

    await stdoutPromise;

    if (exitCode !== 0 && stderr.trim()) {
      events.push({
        type: "relay_error",
        message: stderr.trim(),
        timestamp: new Date().toISOString(),
        cwd: request.cwd,
        agent: this.name,
      });
    }

    for (const event of events) {
      yield event;
    }

    yield {
      type: "relay_exit",
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
    status: "available" | "unavailable";
    stdout?: string;
    stderr?: string;
  }> {
    try {
      const target = buildCodexSpawnTarget([codexBinary, ...buildCodexStatusCommand()]);
      const proc = spawn(target.file, target.args, {
        cwd,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      });

      let stdout = "";
      let stderr = "";

      proc.stdout.on("data", (chunk) => {
        stdout += chunk.toString();
      });

      proc.stderr.on("data", (chunk) => {
        stderr += chunk.toString();
      });

      const code = await new Promise<number>((resolve) => {
        proc.on("close", (value) => resolve(value ?? 1));
      });

      return {
        agent: this.name,
        status: code === 0 ? "available" : "unavailable",
        stdout: stdout.trim(),
        stderr: stderr.trim(),
      };
    } catch (error) {
      return {
        agent: this.name,
        status: "unavailable",
        stderr: error instanceof Error ? error.message : String(error),
      };
    }
  }
}
