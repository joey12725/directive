import assert from "node:assert/strict";
import test from "node:test";
import {
  accumulateOpenCodeUsage,
  buildOpenCodeCommand,
  normalizeOpenCodeUsage,
  parseOpenCodeEvent,
  parseOpenCodeExport,
} from "./opencode.js";

test("buildOpenCodeCommand requests JSON events", () => {
  assert.deepEqual(buildOpenCodeCommand({ prompt: "Say hi", cwd: "C:/workspace" }), [
    "run",
    "--format",
    "json",
    "Say hi",
  ]);
});

test("accumulateOpenCodeUsage aggregates step_finish token usage", () => {
  const usage = accumulateOpenCodeUsage(
    {
      input_tokens: 10,
      output_tokens: 2,
      total_tokens: 12,
      cache_read_input_tokens: 5,
      cache_creation_input_tokens: 1,
      reasoning_tokens: 3,
    },
    {
      type: "step_finish",
      part: {
        tokens: {
          total: 20,
          input: 12,
          output: 8,
          reasoning: 4,
          cache: { read: 6, write: 2 },
        },
      },
    }
  );

  assert.deepEqual(normalizeOpenCodeUsage(usage), {
    input_tokens: 22,
    output_tokens: 10,
    total_tokens: 32,
    cache_read_input_tokens: 11,
    cache_creation_input_tokens: 3,
    reasoning_tokens: 7,
  });
});

test("parseOpenCodeEvent emits assistant text chunks", () => {
  const events = parseOpenCodeEvent({ type: "text", part: { text: "OPEN" } });
  assert.equal(events.length, 1);
  assert.equal(events[0]?.type, "agent_message_chunk");
  if (events[0]?.type === "agent_message_chunk") {
    assert.equal(events[0].text, "OPEN");
  }
});

test("parseOpenCodeExport extracts provider, model, and cost", () => {
  const result = parseOpenCodeExport(
    `Exporting session: ses_test\n${JSON.stringify({
      messages: [
        { info: { role: "assistant", providerID: "openai", modelID: "gpt-5.4", cost: 1.25 } },
        { info: { role: "assistant", providerID: "openai", modelID: "gpt-5.4", cost: 0.75 } },
      ],
    })}`
  );

  assert.deepEqual(result, {
    provider: "openai",
    model: "gpt-5.4",
    totalCostUsd: 2,
  });
});
