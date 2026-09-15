import test from "node:test";
import assert from "node:assert/strict";
import { buildCodexCommand, normalizeCodexUsage, parseCodexEvent } from "./codex.js";

test("buildCodexCommand enables full access when approve_all is true", () => {
  const command = buildCodexCommand({
    prompt: "Ship it",
    cwd: "C:/workspace",
    approve_all: true,
  });

  assert.deepEqual(command, [
    "exec",
    "--json",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
    "-",
  ]);
});

test("normalizeCodexUsage maps cached and reasoning tokens", () => {
  assert.deepEqual(
    normalizeCodexUsage({
      input_tokens: 120,
      cached_input_tokens: 45,
      output_tokens: 30,
      reasoning_output_tokens: 8,
    }),
    {
      input_tokens: 120,
      output_tokens: 30,
      total_tokens: 150,
      cache_read_input_tokens: 45,
      reasoning_tokens: 8,
    }
  );
});

test("parseCodexEvent emits session, chunk, and done data", () => {
  const state: { startedAt: number; sessionId?: string; model: string } = {
    startedAt: Date.now() - 250,
    model: "codex",
  };

  assert.deepEqual(parseCodexEvent({ type: "thread.started", thread_id: "thread-123" }, state), []);
  assert.equal(state.sessionId, "thread-123");

  const chunkEvents = parseCodexEvent(
    {
      type: "item.completed",
      item: {
        type: "agent_message",
        text: "Done.",
      },
    },
    state
  );
  assert.equal(chunkEvents.length, 1);
  assert.equal(chunkEvents[0]?.type, "agent_message_chunk");
  if (chunkEvents[0]?.type === "agent_message_chunk") {
    assert.equal(chunkEvents[0].text, "Done.");
  }

  const doneEvents = parseCodexEvent(
    {
      type: "turn.completed",
      usage: {
        input_tokens: 100,
        cached_input_tokens: 60,
        output_tokens: 20,
      },
    },
    state
  );

  assert.equal(doneEvents.length, 1);
  assert.equal(doneEvents[0]?.type, "done");
  if (doneEvents[0]?.type === "done") {
    assert.equal(doneEvents[0].provider, "openai");
    assert.equal(doneEvents[0].session_id, "thread-123");
    assert.equal(doneEvents[0].usage.total_tokens, 120);
    assert.equal(doneEvents[0].usage.cache_read_input_tokens, 60);
    assert.ok((doneEvents[0].duration_ms ?? 0) >= 0);
  }
});
