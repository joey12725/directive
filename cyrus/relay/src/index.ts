import Fastify from "fastify";
import { spawn } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";
import { pathToFileURL } from "node:url";

type DispatchBody = {
  agent?: string;
  prompt?: string;
  session_name?: string;
  cwd?: string;
  approve_all?: boolean;
};

type ExecBody = {
  agent?: string;
  prompt?: string;
  cwd?: string;
};

const app = Fastify({ logger: true });
const relayPort = Number.parseInt(process.env.CYRUS_RELAY_PORT ?? "7420", 10);
const relaySecret = process.env.CYRUS_RELAY_SECRET ?? "";
const defaultCwd = process.env.CYRUS_RELAY_DEFAULT_CWD || os.homedir();
const acpxBinary = process.platform === "win32" ? "acpx.cmd" : "acpx";
const openClawBinary = process.platform === "win32" ? "openclaw.cmd" : "openclaw";
const claudeBinary = process.platform === "win32" ? "C:\\Users\\you\\.local\\bin\\claude.exe" : "claude";
// On Windows, spawn node directly to avoid cmd.exe quoting issues
const geminiBinary = process.platform === "win32"
  ? "node"
  : "gemini";
const geminiArgs = process.platform === "win32"
  ? [
      "--no-warnings=DEP0040",
      path.join(
        os.homedir(),
        "AppData",
        "Roaming",
        "npm",
        "node_modules",
        "@google",
        "gemini-cli",
        "dist",
        "index.js"
      ),
    ]
  : [];  // On Unix, "gemini" is the wrapper script
const knownAgents = (process.env.CYRUS_RELAY_AGENT_LIST ?? "codex,claude,gemini,openclaw")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const normalizeCwd = (cwd?: string) => (cwd && cwd.trim().length > 0 ? cwd : defaultCwd);
const createHttpError = (statusCode: number, message: string) =>
  Object.assign(new Error(message), {
    statusCode,
  });

const isOpenClawAgent = (agent: string) => agent.trim().toLowerCase() === "openclaw";
const isNativeClaudeAgent = (agent: string) => agent.trim().toLowerCase() === "claude";
const isGeminiAgent = (agent: string) =>
  agent.trim().toLowerCase() === "gemini" || agent.trim().toLowerCase() === "gemini-cli";
const openClawSessionKey = process.env.CYRUS_OPENCLAW_SESSION_KEY ?? "agent:main:main";

const quoteWindowsArg = (value: string) => {
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

const buildSpawnTarget = (command: string[]) => {
  if (process.platform !== "win32") {
    return {
      file: command[0],
      args: command.slice(1),
    };
  }

  const joined = command.map(quoteWindowsArg).join(" ");
  return {
    file: "cmd.exe",
    args: ["/d", "/s", "/c", joined],
  };
};

const buildAcpxCommand = ({
  agent,
  prompt,
  sessionName,
  approveAll = true,
  exec = false,
}: {
  agent: string;
  prompt: string;
  sessionName?: string;
  approveAll?: boolean;
  exec?: boolean;
}) => {
  const command = [acpxBinary, "--format", "json"];

  if (approveAll) {
    command.push("--approve-all");
  }

  command.push(agent);

  if (exec) {
    command.push("exec");
  } else {
    command.push("prompt");
    // WORKAROUND: Don't use named sessions on Windows - let ACPX manage sessions by directory
    // if (sessionName) {
    //   command.push("-s", sessionName);
    // }
  }

  command.push(prompt);
  return command;
};

const ensureSession = async (agent: string, sessionName: string | undefined, cwd: string) => {
  if (isOpenClawAgent(agent)) {
    return { stdout: "", stderr: "", code: 0 };
  }

  if (!sessionName) {
    return { stdout: "", stderr: "", code: 0 };
  }

  // WORKAROUND: acpx sessions ensure is broken on Windows
  // Just skip it and let ACPX create the session on-demand during prompt
  // The session will be created automatically when we send the first prompt
  return { stdout: "", stderr: "", code: 0 };
};

const runToCompletion = async (command: string[], cwd: string) =>
  new Promise<{ stdout: string; stderr: string; code: number | null }>((resolve, reject) => {
    const target = buildSpawnTarget(command);
    const proc = spawn(target.file, target.args, {
      cwd,
      env: process.env,
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

    proc.on("error", reject);
    proc.on("close", (code) => resolve({ stdout, stderr, code }));
  });

type OpenClawSessionSnapshot = {
  key: string;
  sessionId?: string;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  cacheReadTokens?: number;       // Cache read tokens (Anthropic)
  cacheWriteTokens?: number;      // Cache write tokens (Anthropic)
  reasoningTokens?: number;       // Reasoning tokens (o1, R1)
  cost?: number;                  // Cost in USD (if available)
  costUsd?: number;               // Alternative cost field name
  model?: string;
  modelProvider?: string;
  contextTokens?: number;
  agentId?: string;
  kind?: string;
};

type OpenClawHistoryMessage = {
  role?: string;
  content?: Array<{ type?: string; text?: string; thinking?: string }>;
  text?: string;
  timestamp?: number;
  provider?: string;
  model?: string;
};

type OpenClawHistoryResponse = {
  sessionKey?: string;
  sessionId?: string;
  messages?: OpenClawHistoryMessage[];
  thinkingLevel?: string | null;
};

type OpenClawPromptResult = {
  sessionId: string | null;
  sessionKey: string;
  model: string | null;
  provider: string | null;
  outputText: string;
  durationMs: number;
  usage: {
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    cacheReadTokens?: number;
    cacheWriteTokens?: number;
    reasoningTokens?: number;
  };
  cost?: number;
  raw: {
    send: Record<string, unknown>;
    history: OpenClawHistoryResponse;
  };
};

type OpenClawGatewayHelper = {
  callGateway: (opts: Record<string, unknown>) => Promise<any>;
  randomIdempotencyKey: () => string;
};

let openClawGatewayHelperPromise: Promise<OpenClawGatewayHelper> | null = null;

const coerceNumber = (value: unknown) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const extractOpenClawMessageText = (message: OpenClawHistoryMessage | undefined) => {
  if (!message) {
    return "";
  }

  if (typeof message.text === "string" && message.text.trim().length > 0) {
    return message.text.trim();
  }

  return (message.content ?? [])
    .map((entry) => entry?.text?.trim() || "")
    .filter(Boolean)
    .join("\n")
    .trim();
};

const normalizeOpenClawMessageText = (message: OpenClawHistoryMessage | undefined) =>
  extractOpenClawMessageText(message).replace(/\r\n/g, "\n");

const resolveOpenClawDistDir = async () => {
  const candidates = [
    process.env.CYRUS_OPENCLAW_DIST_DIR,
    process.env.APPDATA ? path.join(process.env.APPDATA, "npm", "node_modules", "openclaw", "dist") : undefined,
    process.platform !== "win32" ? "/usr/local/lib/node_modules/openclaw/dist" : undefined,
    process.platform !== "win32" ? "/opt/homebrew/lib/node_modules/openclaw/dist" : undefined,
  ].filter((value): value is string => Boolean(value));

  for (const candidate of candidates) {
    try {
      const stats = await fs.stat(candidate);
      if (stats.isDirectory()) {
        return candidate;
      }
    } catch {
      // Try the next candidate.
    }
  }

  throw new Error("Unable to locate the global OpenClaw dist directory.");
};

const loadOpenClawGatewayHelper = async () => {
  if (!openClawGatewayHelperPromise) {
    openClawGatewayHelperPromise = (async () => {
      const distDir = await resolveOpenClawDistDir();
      const files = await fs.readdir(distDir);
      const callModule = files
        .filter((file) => /^call-.*\.js$/u.test(file))
        .sort()[0];

      if (!callModule) {
        throw new Error("Unable to find the OpenClaw gateway helper module.");
      }

      const moduleUrl = pathToFileURL(path.join(distDir, callModule)).href;
      const helperModule = await import(moduleUrl);

      return {
        callGateway: helperModule.n as OpenClawGatewayHelper["callGateway"],
        randomIdempotencyKey: helperModule.a as OpenClawGatewayHelper["randomIdempotencyKey"],
      };
    })();
  }

  return openClawGatewayHelperPromise;
};

const loadOpenClawGatewayConfig = async () => {
  const configPath = process.env.OPENCLAW_CONFIG_PATH ?? path.join(os.homedir(), ".openclaw", "openclaw.json");
  const rawConfig = await fs.readFile(configPath, "utf8");
  const config = JSON.parse(rawConfig) as {
    gateway?: {
      auth?: {
        token?: string;
      };
      remote?: {
        url?: string;
      };
    };
  };

  const token = config.gateway?.auth?.token?.trim();
  if (!token) {
    throw new Error("OpenClaw gateway auth token is missing from the local configuration.");
  }

  return {
    url: config.gateway?.remote?.url?.trim() || "ws://127.0.0.1:18789",
    token,
  };
};

const getOpenClawSessionSnapshot = async (cwd: string, sessionKey: string) => {
  const result = await runToCompletion([openClawBinary, "sessions", "--json"], cwd);
  if (result.code !== 0) {
    throw new Error(result.stderr.trim() || "Unable to read OpenClaw session state.");
  }

  const parsed = JSON.parse(result.stdout) as { sessions?: OpenClawSessionSnapshot[] };
  return parsed.sessions?.find((session) => session.key === sessionKey) ?? null;
};

const callOpenClawGateway = async (
  method: string,
  params: Record<string, unknown>,
  timeoutMs: number,
  expectFinal = false
) => {
  const helper = await loadOpenClawGatewayHelper();
  const config = await loadOpenClawGatewayConfig();

  return helper.callGateway({
    url: config.url,
    token: config.token,
    method,
    params,
    timeoutMs,
    expectFinal,
    clientName: "cli",
    mode: "cli",
  });
};

const runOpenClawPrompt = async (prompt: string, cwd: string): Promise<OpenClawPromptResult> => {
  const helper = await loadOpenClawGatewayHelper();
  const sessionKey = openClawSessionKey;
  const beforeSnapshot = await getOpenClawSessionSnapshot(cwd, sessionKey);
  const beforeHistory = (await callOpenClawGateway(
    "chat.history",
    { sessionKey, limit: 20 },
    30_000
  )) as OpenClawHistoryResponse;
  const beforeLastTimestamp = Math.max(...(beforeHistory.messages ?? []).map((message) => message.timestamp ?? 0), 0);
  const sendStartedAt = Date.now();
  const message = `[Working directory: ${cwd}]\n\n${prompt}`;
  const sendResult = (await callOpenClawGateway(
    "chat.send",
    {
      sessionKey,
      message,
      idempotencyKey: helper.randomIdempotencyKey(),
      deliver: false,
    },
    120_000,
    true
  )) as Record<string, unknown>;

  let latestHistory = beforeHistory;
  let latestAssistant: OpenClawHistoryMessage | undefined;
  const deadline = Date.now() + 120_000;
  const normalizedMessage = message.replace(/\r\n/g, "\n");

  while (Date.now() < deadline) {
    latestHistory = (await callOpenClawGateway(
      "chat.history",
      { sessionKey, limit: 20 },
      30_000
    )) as OpenClawHistoryResponse;

    const messages = latestHistory.messages ?? [];
    const matchedUserIndex = messages.findIndex(
      (entry) =>
        entry.role === "user" &&
        (entry.timestamp ?? 0) > beforeLastTimestamp &&
        normalizeOpenClawMessageText(entry) === normalizedMessage
    );

    if (matchedUserIndex >= 0) {
      latestAssistant = messages
        .slice(matchedUserIndex + 1)
        .find((entry) => entry.role === "assistant");
    }

    if (latestAssistant) {
      break;
    }

    await sleep(1_000);
  }

  if (!latestAssistant) {
    throw new Error("Timed out waiting for the OpenClaw desktop session to reply.");
  }

  const afterSnapshot = await getOpenClawSessionSnapshot(cwd, sessionKey);

  // Calculate token deltas
  const inputTokensDelta = Math.max(
    coerceNumber(afterSnapshot?.inputTokens) - coerceNumber(beforeSnapshot?.inputTokens),
    0
  );
  const outputTokensDelta = Math.max(
    coerceNumber(afterSnapshot?.outputTokens) - coerceNumber(beforeSnapshot?.outputTokens),
    0
  );
  const totalTokensDelta = Math.max(
    coerceNumber(afterSnapshot?.totalTokens) - coerceNumber(beforeSnapshot?.totalTokens),
    0
  );

  // Calculate cache token deltas (if available - Anthropic)
  const cacheReadDelta = afterSnapshot?.cacheReadTokens !== undefined && beforeSnapshot?.cacheReadTokens !== undefined
    ? Math.max(coerceNumber(afterSnapshot.cacheReadTokens) - coerceNumber(beforeSnapshot.cacheReadTokens), 0)
    : undefined;

  const cacheWriteDelta = afterSnapshot?.cacheWriteTokens !== undefined && beforeSnapshot?.cacheWriteTokens !== undefined
    ? Math.max(coerceNumber(afterSnapshot.cacheWriteTokens) - coerceNumber(beforeSnapshot.cacheWriteTokens), 0)
    : undefined;

  // Calculate reasoning tokens delta (if available - o1, R1)
  const reasoningDelta = afterSnapshot?.reasoningTokens !== undefined && beforeSnapshot?.reasoningTokens !== undefined
    ? Math.max(coerceNumber(afterSnapshot.reasoningTokens) - coerceNumber(beforeSnapshot.reasoningTokens), 0)
    : undefined;

  // Extract cost (if available)
  const cost = afterSnapshot?.cost ?? afterSnapshot?.costUsd;
  const costDelta = cost !== undefined && beforeSnapshot?.cost !== undefined
    ? Math.max(coerceNumber(cost) - coerceNumber(beforeSnapshot.cost), 0)
    : cost;

  return {
    sessionId: latestHistory.sessionId ?? afterSnapshot?.sessionId ?? beforeSnapshot?.sessionId ?? null,
    sessionKey,
    model: latestAssistant.model ?? afterSnapshot?.model ?? beforeSnapshot?.model ?? null,
    provider: latestAssistant.provider ?? afterSnapshot?.modelProvider ?? beforeSnapshot?.modelProvider ?? null,
    outputText: extractOpenClawMessageText(latestAssistant),
    durationMs: Math.max(Date.now() - sendStartedAt, 0),
    usage: {
      inputTokens: inputTokensDelta,
      outputTokens: outputTokensDelta,
      totalTokens: totalTokensDelta,
      cacheReadTokens: cacheReadDelta,
      cacheWriteTokens: cacheWriteDelta,
      reasoningTokens: reasoningDelta,
    },
    cost: costDelta,
    raw: {
      send: sendResult,
      history: latestHistory,
    },
  };
};

const buildOpenClawEvents = (result: OpenClawPromptResult, agent: string, cwd: string) => {
  const events: Array<Record<string, unknown>> = [];
  if (result.outputText) {
    events.push({
      type: "agent_message_chunk",
      text: result.outputText,
      timestamp: new Date().toISOString(),
    });
  }

  // Build usage object with all available token metrics
  const usage: Record<string, number> = {
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

  const doneEvent: Record<string, unknown> = {
    type: "done",
    timestamp: new Date().toISOString(),
    model: result.model,
    provider: result.provider,
    session_id: result.sessionId,
    session_key: result.sessionKey,
    duration_ms: result.durationMs,
    usage,
  };

  // Add cost if available
  if (result.cost !== undefined) {
    doneEvent.total_cost_usd = result.cost;
  }

  events.push(doneEvent);

  events.push({
    type: "relay_exit",
    code: 0,
    timestamp: new Date().toISOString(),
    cwd,
    agent,
  });

  return events;
};

const buildOpenClawExecResult = (result: OpenClawPromptResult) => {
  // Build usage object with all available token metrics
  const usage: Record<string, number> = {
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

  const execResult: Record<string, unknown> = {
    code: 0,
    stdout: JSON.stringify(result.raw),
    stderr: "",
    output_text: result.outputText,
    session_id: result.sessionId,
    session_key: result.sessionKey,
    model: result.model,
    provider: result.provider,
    duration_ms: result.durationMs,
    usage,
    raw: result.raw,
  };

  // Add cost if available
  if (result.cost !== undefined) {
    execResult.total_cost_usd = result.cost;
  }

  return execResult;
};

const ensureAuthorized = async (authorization?: string) => {
  if (!relaySecret) return;
  const token = authorization?.replace(/^Bearer\s+/i, "");
  if (token !== relaySecret) {
    throw createHttpError(401, "Missing or invalid relay token.");
  }
};

app.addHook("onRequest", async (request) => {
  await ensureAuthorized(request.headers.authorization);
});

app.get("/health", async () => ({
  status: "ok",
  service: "cyrus-relay",
  uptime: process.uptime(),
  hostname: os.hostname(),
  defaultCwd,
  agents: knownAgents,
}));

app.get("/agents", async () => {
  const results = await Promise.all(
    knownAgents.map(async (agent) => {
      try {
        let command: string[];
        if (isOpenClawAgent(agent)) {
          command = [openClawBinary, "status"];
        } else if (isGeminiAgent(agent)) {
          command = [geminiBinary, ...geminiArgs, "--version"];
        } else {
          command = [acpxBinary, "--format", "json", agent, "status"];
        }
        const result = await runToCompletion(command, defaultCwd);
        return {
          agent,
          status: result.code === 0 ? "available" : "unavailable",
          stdout: result.stdout.trim(),
          stderr: result.stderr.trim(),
        };
      } catch (error) {
        return {
          agent,
          status: "unavailable",
          stderr: error instanceof Error ? error.message : String(error),
        };
      }
    })
  );

  return { agents: results };
});

app.post<{ Body: DispatchBody }>("/dispatch", async (request, reply) => {
  const agent = request.body.agent ?? "codex";
  const prompt = request.body.prompt?.trim();

  if (!prompt) {
    throw createHttpError(400, "A prompt is required.");
  }

  const cwd = normalizeCwd(request.body.cwd);
  if (isOpenClawAgent(agent)) {
    const result = await runOpenClawPrompt(prompt, cwd);

    reply.raw.writeHead(200, {
      "Content-Type": "application/x-ndjson",
      "Transfer-Encoding": "chunked",
    });

    try {
      for (const event of buildOpenClawEvents(result, agent, cwd)) {
        reply.raw.write(`${JSON.stringify(event)}\n`);
      }
    } catch (error) {
      reply.raw.write(
        `${JSON.stringify({
          type: "relay_error",
          message: error instanceof Error ? error.message : String(error),
          raw: result.raw,
          timestamp: new Date().toISOString(),
          cwd,
          agent,
        })}\n`
      );
      reply.raw.write(
        `${JSON.stringify({ type: "relay_exit", code: 1, timestamp: new Date().toISOString(), cwd, agent })}\n`
      );
    }

    reply.raw.end();
    return reply;
  }

  // Native Gemini CLI integration
  if (isGeminiAgent(agent)) {
    reply.raw.writeHead(200, {
      "Content-Type": "application/x-ndjson",
      "Transfer-Encoding": "chunked",
    });

    app.log.info({ agent, prompt: prompt.substring(0, 50) }, "Spawning Gemini");

    const proc = spawn(
      geminiBinary,
      [...geminiArgs, "--prompt", prompt, "--output-format", "stream-json", "--yolo"],
      {
        cwd,
        env: process.env,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );

    let buffer = "";
    let geminiModel = "unknown";
    let sessionId: string | undefined;

    proc.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;

        try {
          const event = JSON.parse(line);

          if (event.type === "init") {
            sessionId = event.session_id;
            geminiModel = event.model;
          } else if (event.type === "message" && event.role === "assistant") {
            const text = event.content || "";
            if (text) {
              reply.raw.write(
                `${JSON.stringify({
                  type: "agent_message_chunk",
                  text,
                  timestamp: new Date().toISOString(),
                })}\n`
              );
            }
          } else if (event.type === "result") {
            const stats = event.stats || {};
            reply.raw.write(
              `${JSON.stringify({
                type: "done",
                timestamp: new Date().toISOString(),
                model: geminiModel,
                session_id: sessionId || "unknown",
                usage: {
                  input_tokens: stats.input_tokens || 0,
                  output_tokens: stats.output_tokens || 0,
                  total_tokens: stats.total_tokens || (stats.input_tokens + stats.output_tokens) || 0,
                  cache_read_input_tokens: stats.cached || 0,
                },
                duration_ms: stats.duration_ms,
              })}\n`
            );
          }
        } catch (error) {
          app.log.warn({ line, error }, "Failed to parse Gemini stream event");
        }
      }
    });

    proc.stderr.on("data", (chunk) => {
      app.log.warn({ stderr: chunk.toString() }, "gemini stderr");
    });

    proc.on("close", (code) => {
      reply.raw.write(
        `${JSON.stringify({
          type: "relay_exit",
          code: code ?? 0,
          timestamp: new Date().toISOString(),
          cwd,
          agent,
        })}\n`
      );
      reply.raw.end();
    });

    proc.on("error", (error) => {
      reply.raw.write(
        `${JSON.stringify({
          type: "relay_error",
          message: error.message,
          timestamp: new Date().toISOString(),
          cwd,
          agent,
        })}\n`
      );
      reply.raw.end();
    });

    return reply;
  }

  // Native Claude Code integration (bypass ACPX)
  if (isNativeClaudeAgent(agent)) {
    reply.raw.writeHead(200, {
      "Content-Type": "application/x-ndjson",
      "Transfer-Encoding": "chunked",
    });

    const proc = spawn(
      claudeBinary,
      ["--print", "--output-format", "stream-json", "--verbose", prompt],
      {
        cwd,
        env: process.env,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );

    let buffer = "";
    let claudeModel = "claude-sonnet-4-5-20250929";
    let sessionId: string | undefined;
    let totalUsage: any = {};
    let responseText = "";

    proc.stdout.on("data", (chunk) => {
      buffer += chunk.toString();
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;

        try {
          const event = JSON.parse(line);

          // Transform Claude events to ACPXDispatcher format
          if (event.type === "system" && event.subtype === "init") {
            sessionId = event.session_id;
            claudeModel = event.model;
          } else if (event.type === "assistant") {
            // Extract text from assistant message
            const text = event.message?.content?.find((c: any) => c.type === "text")?.text || "";
            if (text) {
              responseText += text;
              reply.raw.write(
                `${JSON.stringify({
                  type: "agent_message_chunk",
                  text,
                  timestamp: new Date().toISOString(),
                })}\n`
              );
            }
            // Track usage
            if (event.message?.usage) {
              totalUsage = event.message.usage;
            }
          } else if (event.type === "result") {
            // Send done event with FULL usage including all tool calls
            const usage = event.usage || totalUsage;

            // Parse modelUsage to get actual token counts across ALL models and tool calls
            let totalInputTokens = 0;
            let totalOutputTokens = 0;
            let totalCacheRead = usage.cache_read_input_tokens || 0;
            let totalCacheCreation = usage.cache_creation_input_tokens || 0;
            const modelBreakdown: any = {};

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

            reply.raw.write(
              `${JSON.stringify({
                type: "done",
                timestamp: new Date().toISOString(),
                model: claudeModel,
                session_id: sessionId,
                num_turns: event.num_turns || 1,
                usage: {
                  input_tokens: totalInputTokens,
                  output_tokens: totalOutputTokens,
                  total_tokens: totalInputTokens + totalOutputTokens,
                  cache_read_input_tokens: totalCacheRead,
                  cache_creation_input_tokens: totalCacheCreation,
                },
                model_breakdown: modelBreakdown,
                total_cost_usd: event.total_cost_usd,
                duration_ms: event.duration_ms,
                duration_api_ms: event.duration_api_ms,
              })}\n`
            );
          }
        } catch (error) {
          app.log.warn({ line, error }, "Failed to parse Claude stream event");
        }
      }
    });

    proc.stderr.on("data", (chunk) => {
      app.log.warn({ stderr: chunk.toString() }, "claude stderr");
    });

    proc.on("close", (code) => {
      reply.raw.write(
        `${JSON.stringify({
          type: "relay_exit",
          code: code ?? 0,
          timestamp: new Date().toISOString(),
          cwd,
          agent,
        })}\n`
      );
      reply.raw.end();
    });

    proc.on("error", (error) => {
      reply.raw.write(
        `${JSON.stringify({
          type: "relay_error",
          message: error.message,
          timestamp: new Date().toISOString(),
          cwd,
          agent,
        })}\n`
      );
      reply.raw.end();
    });

    return reply;
  }

  const ensureResult = await ensureSession(agent, request.body.session_name, cwd);
  if (ensureResult.code !== 0) {
    reply.raw.writeHead(500, {
      "Content-Type": "application/json",
    });
    reply.raw.end(
      JSON.stringify({
        error: "Failed to ensure ACPX session.",
        agent,
        cwd,
        stdout: ensureResult.stdout.trim(),
        stderr: ensureResult.stderr.trim(),
        code: ensureResult.code,
      })
    );
    return reply;
  }

  const command = buildAcpxCommand({
    agent,
    prompt,
    sessionName: request.body.session_name,
    approveAll: request.body.approve_all ?? true,
  });

  reply.raw.writeHead(200, {
    "Content-Type": "application/x-ndjson",
    "Transfer-Encoding": "chunked",
  });

  const target = buildSpawnTarget(command);
  const proc = spawn(target.file, target.args, {
    cwd,
    env: process.env,
    shell: false,
    stdio: ["ignore", "pipe", "pipe"],
  });

  proc.stdout.on("data", (chunk) => {
    reply.raw.write(chunk);
  });

  proc.stderr.on("data", (chunk) => {
    app.log.warn({ stderr: chunk.toString() }, "acpx stderr");
  });

  proc.on("close", (code) => {
    reply.raw.write(
      `${JSON.stringify({ type: "relay_exit", code, timestamp: new Date().toISOString(), cwd, agent })}\n`
    );
    reply.raw.end();
  });

  proc.on("error", (error) => {
    reply.raw.write(
      `${JSON.stringify({
        type: "relay_error",
        message: error.message,
        timestamp: new Date().toISOString(),
        cwd,
        agent,
      })}\n`
    );
    reply.raw.end();
  });

  return reply;
});

app.post<{ Body: ExecBody }>("/exec", async (request) => {
  const agent = request.body.agent ?? "codex";
  const prompt = request.body.prompt?.trim();

  if (!prompt) {
    throw createHttpError(400, "A prompt is required.");
  }

  const cwd = normalizeCwd(request.body.cwd);
  if (isOpenClawAgent(agent)) {
    const result = await runOpenClawPrompt(prompt, cwd);
    return buildOpenClawExecResult(result);
  }

  // Native Gemini CLI integration
  if (isGeminiAgent(agent)) {
    const proc = spawn(
      geminiBinary,
      [...geminiArgs, "--prompt", prompt, "--output-format", "stream-json", "--yolo"],
      {
        cwd,
        env: process.env,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
      }
    );

    // app.log.info({ target }, "Spawning Gemini"); // Removed logging of target as we don't use buildSpawnTarget here

    let buffer = "";
    let geminiModel = "unknown";
    let sessionId: string | undefined;
    let outputText = "";
    let stats: any = {};

    await new Promise<void>((resolve, reject) => {
      proc.stdout.on("data", (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.trim()) continue;

          try {
            const event = JSON.parse(line);
            if (event.type === "init") {
              sessionId = event.session_id;
              geminiModel = event.model;
            } else if (event.type === "message" && event.role === "assistant") {
              outputText += event.content || "";
            } else if (event.type === "result") {
              stats = event.stats || {};
            }
          } catch (error) {
            app.log.warn({ line, error }, "Failed to parse Gemini stream event");
          }
        }
      });

      proc.on("close", (code) => {
        if (code === 0 || code === null) {
          resolve();
        } else {
          reject(new Error(`Gemini CLI exited with code ${code}`));
        }
      });

      proc.on("error", (error) => reject(error));
    });

    return {
      code: 0,
      stdout: outputText,
      stderr: "",
      output_text: outputText,
      session_id: sessionId,
      model: geminiModel,
      duration_ms: stats.duration_ms,
      usage: {
        input_tokens: stats.input_tokens || 0,
        output_tokens: stats.output_tokens || 0,
        total_tokens: stats.total_tokens || (stats.input_tokens + stats.output_tokens) || 0,
        cache_read_input_tokens: stats.cached || 0,
      },
    };
  }

  if (isNativeClaudeAgent(agent)) {
    // Direct spawn without cmd.exe wrapper for Windows
    const result = await new Promise<{ stdout: string; stderr: string; code: number | null }>((resolve, reject) => {
      const proc = spawn(claudeBinary, ["--print", "--output-format", "text", prompt], {
        cwd,
        env: process.env,
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

      proc.on("error", reject);
      proc.on("close", (code) => resolve({ stdout, stderr, code }));
    });

    return {
      ...result,
      output_text: result.stdout.trim(),
      model: "claude-sonnet-4.5",
    };
  }

  const command = buildAcpxCommand({ agent, prompt, exec: true });
  return runToCompletion(command, cwd);
});

app.get<{ Querystring: { agent?: string } }>("/sessions", async (request) => {
  const agent = request.query.agent ?? "codex";
  return runToCompletion([acpxBinary, "--format", "json", agent, "sessions", "list"], defaultCwd);
});

app.post<{ Body: { agent?: string; session_id?: string } }>("/cancel", async (request) => {
  const agent = request.body.agent ?? "codex";
  const sessionId = request.body.session_id?.trim();

  if (!sessionId) {
    throw createHttpError(400, "A session_id is required.");
  }

  return runToCompletion([acpxBinary, agent, "sessions", "cancel", sessionId], defaultCwd);
});

app.get<{ Querystring: { cwd?: string; file?: string } }>("/workspace-files", async (request) => {
  const cwd = normalizeCwd(request.query.cwd);
  const target = request.query.file ? path.resolve(cwd, request.query.file) : cwd;

  const stats = await fs.stat(target);
  if (stats.isDirectory()) {
    const entries = await fs.readdir(target, { withFileTypes: true });
    return {
      cwd,
      entries: entries.map((entry) => ({
        name: entry.name,
        type: entry.isDirectory() ? "directory" : "file",
      })),
    };
  }

  return {
    cwd,
    file: path.relative(cwd, target),
    content: await fs.readFile(target, "utf8"),
  };
});

app.post<{ Body: { cwd?: string; file?: string; content?: string } }>("/workspace-files", async (request) => {
  const cwd = normalizeCwd(request.body.cwd);
  const relativeFile = request.body.file?.trim();
  if (!relativeFile) {
    throw createHttpError(400, "A file path is required.");
  }

  const target = path.resolve(cwd, relativeFile);
  await fs.mkdir(path.dirname(target), { recursive: true });
  await fs.writeFile(target, request.body.content ?? "", "utf8");
  return { ok: true, file: path.relative(cwd, target) };
});

app.listen({ port: relayPort, host: "0.0.0.0" }).catch((error) => {
  app.log.error(error);
  process.exit(1);
});
