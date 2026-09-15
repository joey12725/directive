import { spawn } from "node:child_process";
import { AgentRunner, type PromptRequest, dispatchToExec } from "./base.js";
import type { AgentEvent, ExecResult, TokenUsage } from "../types/agent-events.js";

export const openCodeBinary = process.platform === "win32" ? "opencode.exe" : "opencode";

type OpenCodeUsageState = {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
  reasoning_tokens: number;
};

type OpenCodeSessionInfo = {
  provider?: string;
  model?: string;
  totalCostUsd?: number;
};

type OpenCodeStreamEvent = {
  type?: string;
  sessionID?: string;
  part?: {
    text?: string;
    reason?: string;
    cost?: number;
    tokens?: {
      total?: number;
      input?: number;
      output?: number;
      reasoning?: number;
      cache?: {
        read?: number;
        write?: number;
      };
    };
  };
};

type OpenCodeExportMessage = {
  info?: {
    role?: string;
    modelID?: string;
    providerID?: string;
    cost?: number;
  };
};

const createUsageState = (): OpenCodeUsageState => ({
  input_tokens: 0,
  output_tokens: 0,
  total_tokens: 0,
  cache_read_input_tokens: 0,
  cache_creation_input_tokens: 0,
  reasoning_tokens: 0,
});

const toNumber = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const buildOpenCodeCommand = (request: PromptRequest): string[] => ["run", "--format", "json", request.prompt];

export const buildOpenCodeStatusCommand = (): string[] => ["--version"];

export const normalizeOpenCodeUsage = (usage: OpenCodeUsageState): TokenUsage => ({
  input_tokens: usage.input_tokens,
  output_tokens: usage.output_tokens,
  total_tokens: usage.total_tokens,
  cache_read_input_tokens: usage.cache_read_input_tokens || undefined,
  cache_creation_input_tokens: usage.cache_creation_input_tokens || undefined,
  reasoning_tokens: usage.reasoning_tokens || undefined,
});

export const accumulateOpenCodeUsage = (usage: OpenCodeUsageState, event: OpenCodeStreamEvent): OpenCodeUsageState => {
  if (event.type !== "step_finish") {
    return usage;
  }

  const tokens = event.part?.tokens;
  return {
    input_tokens: usage.input_tokens + toNumber(tokens?.input),
    output_tokens: usage.output_tokens + toNumber(tokens?.output),
    total_tokens: usage.total_tokens + toNumber(tokens?.total),
    cache_read_input_tokens: usage.cache_read_input_tokens + toNumber(tokens?.cache?.read),
    cache_creation_input_tokens: usage.cache_creation_input_tokens + toNumber(tokens?.cache?.write),
    reasoning_tokens: usage.reasoning_tokens + toNumber(tokens?.reasoning),
  };
};

export const parseOpenCodeEvent = (rawEvent: unknown): AgentEvent[] => {
  if (!rawEvent || typeof rawEvent !== "object") {
    return [];
  }

  const event = rawEvent as OpenCodeStreamEvent;
  if (event.type !== "text") {
    return [];
  }

  const text = event.part?.text;
  if (!text) {
    return [];
  }

  return [
    {
      type: "agent_message_chunk",
      text,
      timestamp: new Date().toISOString(),
    },
  ];
};

export const parseOpenCodeExport = (stdout: string): OpenCodeSessionInfo => {
  const jsonStart = stdout.indexOf("{");
  if (jsonStart === -1) {
    return {};
  }

  try {
    const parsed = JSON.parse(stdout.slice(jsonStart)) as { messages?: OpenCodeExportMessage[] };
    const assistantMessages = (parsed.messages ?? []).filter((message) => message.info?.role === "assistant");
    const latest = assistantMessages.at(-1)?.info;

    return {
      provider: latest?.providerID,
      model: latest?.modelID,
      totalCostUsd: assistantMessages.reduce((sum, message) => sum + toNumber(message.info?.cost), 0),
    };
  } catch {
    return {};
  }
};

const loadOpenCodeSessionInfo = async (cwd: string, sessionId?: string): Promise<OpenCodeSessionInfo> => {
  if (!sessionId) {
    return {};
  }

  try {
    const proc = spawn(openCodeBinary, ["export", sessionId], {
      cwd,
      env: process.env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    proc.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });

    const code = await new Promise<number>((resolve) => {
      proc.on("close", (value) => resolve(value ?? 1));
      proc.on("error", () => resolve(1));
    });

    if (code !== 0) {
      return {};
    }

    return parseOpenCodeExport(stdout);
  } catch {
    return {};
  }
};

export class OpenCodeRunner extends AgentRunner {
  readonly name = "opencode";

  canHandle(agent: string): boolean {
    return agent.trim().toLowerCase() === "opencode";
  }

  async *dispatch(request: PromptRequest): AsyncGenerator<AgentEvent, void, unknown> {
    const proc = spawn(openCodeBinary, buildOpenCodeCommand(request), {
      cwd: request.cwd,
      env: process.env,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let buffer = "";
    let stderr = "";
    let sessionId: string | undefined;
    let usage = createUsageState();
    const startedAt = Date.now();
    const events: AgentEvent[] = [];

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
            const parsed = JSON.parse(line) as OpenCodeStreamEvent;
            sessionId = parsed.sessionID ?? sessionId;
            usage = accumulateOpenCodeUsage(usage, parsed);
            events.push(...parseOpenCodeEvent(parsed));
          } catch {
            events.push({
              type: "relay_error",
              message: `Failed to parse OpenCode event: ${line}`,
              timestamp: new Date().toISOString(),
              cwd: request.cwd,
              agent: this.name,
              raw: line,
            });
          }
        }
      });

      proc.stdout.on("end", resolve);
    });

    proc.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });

    const exitCode = await new Promise<number>((resolve) => {
      proc.on("close", (code) => resolve(code ?? 1));
      proc.on("error", () => resolve(1));
    });

    await stdoutPromise;

    const sessionInfo = await loadOpenCodeSessionInfo(request.cwd, sessionId);

    if (exitCode !== 0 && stderr.trim()) {
      events.push({
        type: "relay_error",
        message: stderr.trim(),
        timestamp: new Date().toISOString(),
        cwd: request.cwd,
        agent: this.name,
      });
    }

    events.push({
      type: "done",
      timestamp: new Date().toISOString(),
      model: sessionInfo.model ?? process.env.CYRUS_OPENCODE_MODEL ?? "unknown",
      provider: sessionInfo.provider,
      session_id: sessionId ?? "unknown",
      usage: normalizeOpenCodeUsage(usage),
      total_cost_usd: sessionInfo.totalCostUsd,
      duration_ms: Date.now() - startedAt,
    });

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
      const proc = spawn(openCodeBinary, buildOpenCodeStatusCommand(), {
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
