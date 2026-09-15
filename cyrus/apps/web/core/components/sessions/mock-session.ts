/**
 * Mock session data for development and visual testing.
 * Covers all event types: text, tool_call, thinking, error, system events.
 */

import type { Session } from "./types";

export const MOCK_SESSION: Session = {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  agent: "d7860f49-534d-47e7-bff8-420d1c9eecba",
  agent_name: "Cyrus PM",
  goal: "26720ae9-c197-4890-8825-673bc748a181",
  goal_name: "Ship Dashboard v1",
  project: "f1234567-abcd-ef01-2345-67890abcdef0",
  project_name: "Cyrus Core",
  work_item: "98765432-dcba-0fed-5432-10fedcba9876",
  work_item_name: "CYR-42: Build session replay viewer",
  pool: "12cc18c7-803a-43c7-a9e8-fa6b8eca54f8",
  pool_name: "Anthropic Subscription",
  acpx_session_id: "acpx-session-demo-001",
  started_at: "2026-03-18T10:30:00Z",
  ended_at: "2026-03-18T10:34:12Z",
  status: "completed",
  event_log: [
    {
      type: "session_started",
      session_id: "acpx-session-demo-001",
      model: "claude-sonnet-4-5-20250514",
    },
    {
      type: "thinking",
      content:
        "The user wants me to build a session replay viewer component. Let me first understand the existing codebase structure, then plan the component hierarchy. I need to handle multiple event types: text, tool_call, thinking, and error. I should also consider responsive layout with a metadata sidebar.\n\nLet me start by reading the existing session model to understand the data shape.",
    },
    {
      type: "text",
      text: "I'll build the session replay viewer. Let me start by examining the existing data model and then create the components.",
    },
    {
      type: "tool_call",
      tool_name: "read_file",
      tool_args: { path: "cyrus/apps/api/plane/db/models/cyrus.py", start_line: 330, end_line: 380 },
      tool_output:
        'class CyrusSession(BaseModel):\n    agent = models.ForeignKey(Agent, on_delete=models.PROTECT)\n    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True)\n    status = models.CharField(max_length=20, choices=SessionStatus.choices)\n    event_log = models.JSONField(default=list)\n    total_tokens = models.IntegerField(default=0)\n    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6)',
      tool_status: "success",
    },
    {
      type: "thinking",
      content: "Good — the session model stores event_log as a JSONField. Now I need to create the TypeScript types and the renderer components.",
    },
    {
      type: "text",
      text: "The session model stores `event_log` as a JSON array. I'll create TypeScript types matching this structure and build individual renderers for each event type.",
    },
    {
      type: "tool_call",
      tool_name: "write_file",
      tool_args: { path: "web/core/components/sessions/types.ts" },
      tool_output: "File written successfully.",
      tool_status: "success",
    },
    {
      type: "tool_call",
      tool_name: "write_file",
      tool_args: { path: "web/core/components/sessions/event-renderers.tsx" },
      tool_output: "File written successfully.",
      tool_status: "success",
    },
    {
      type: "tool_call",
      tool_name: "run_command",
      tool_args: { command: "pnpm check:types" },
      tool_output: "error TS2307: Cannot find module '@plane/propel/accordion'.",
      tool_status: "error",
    },
    {
      type: "error",
      error: "TypeScript compilation failed: Cannot find module '@plane/propel/accordion'",
      error_code: "TS2307",
    },
    {
      type: "text",
      text: "The accordion import path is incorrect — the propel package uses a different export. Let me fix the import and use the correct component API.",
    },
    {
      type: "tool_call",
      tool_name: "edit_file",
      tool_args: { path: "web/core/components/sessions/event-renderers.tsx", old: "from '@plane/propel/accordion'", new: "from '@plane/propel/collapsible'" },
      tool_output: "Edit applied successfully.",
      tool_status: "success",
    },
    {
      type: "tool_call",
      tool_name: "run_command",
      tool_args: { command: "pnpm check:types" },
      tool_output: "No errors found.",
      tool_status: "success",
    },
    {
      type: "text",
      text: "All TypeScript errors resolved. The session replay viewer is complete with:\n- Event timeline with text, tool call, thinking, and error renderers\n- Metadata sidebar with agent info, tokens, cost, and Langfuse link\n- Responsive layout using Tailwind grid",
    },
    {
      type: "done",
      session_id: "acpx-session-demo-001",
      model: "claude-sonnet-4-5-20250514",
      usage: {
        input_tokens: 12400,
        output_tokens: 3200,
        total_tokens: 15600,
        cache_read_input_tokens: 8000,
      },
    },
  ],
  summary: "Built the session replay viewer with event timeline and metadata sidebar. Fixed one TypeScript import error along the way.",
  outcome: { files_created: 4, files_modified: 1, errors_resolved: 1 },
  total_tokens: 15600,
  input_tokens: 12400,
  output_tokens: 3200,
  estimated_cost_usd: "0.045600",
  duration_seconds: 252,
  model_name: "claude-sonnet-4-5-20250514",
  was_rate_limited: false,
  rate_limit_wait_seconds: 0,
  langfuse_trace_id: "trace-demo-001",
  langfuse_trace_url: "https://cloud.langfuse.com/trace/trace-demo-001",
  created_at: "2026-03-18T10:30:00Z",
  updated_at: "2026-03-18T10:34:12Z",
};
