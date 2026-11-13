# Extending Directive

## Add a coding agent to the relay

The relay speaks one event schema no matter which CLI is underneath. To support a new CLI:

1. **Write the adapter.** Copy `cyrus/relay/src/agents/TEMPLATE.ts` to `src/agents/<name>.ts`. The template shows the contract: build the command line, spawn the process in the requested `cwd`, parse its output line by line, and yield
   - zero or more `agent_message_chunk` events with streamed text,
   - exactly one `done` event with `usage` (input, output, total, optional cache and reasoning tokens), `model`, `session_id` and, if known, `total_cost_usd` and `model_breakdown`,
   - exactly one `relay_exit` event with the process exit code, plus `relay_error` if anything failed.

   Keep the parsing in pure exported functions (`buildXCommand`, `parseXEvent`, `normalizeXUsage`) so they are easy to test. `codex.ts` and `opencode.ts` follow this pattern.
2. **Register it.** Add the runner to `createAgentFactory()` in `src/agents/index.ts`, import its helpers in `src/index.ts`, and add a branch for the agent name in the `/dispatch` and `/exec` handlers next to the existing ones.
3. **Test it.** Add `src/agents/<name>.test.ts` using `node:test` (see `codex.test.ts`), and list it in the relay's `test` script.
4. **Advertise it.** Add the name to `CYRUS_RELAY_AGENT_LIST` and, on the API side, add a value to `AgentType` in `plane/db/models/cyrus.py` if you want it selectable as its own type (this needs a migration).

Then register an `Agent` whose `acpx_agent_name` matches the relay name.

## Add an orchestrator tool

Tools are plain functions in `cyrus/apps/api/plane/app/orchestrator/tools.py` with the signature `(args: dict) -> dict`.

1. Write the function. Use `_resolve_context(args)` to get the workspace, project and acting agent, and raise `CyrusToolError` for bad input so the CLI returns a clean error.
2. Add it to `TOOL_REGISTRY` at the bottom of the file.

It is immediately available to every agent as:

```bash
python manage.py cyrus_tool my_new_tool '{"workspace_id": "...", "foo": "bar"}'
```

Mention the tool in the PM agent's prompt or loop instructions so it knows when to call it.

## Add an autonomous loop

Loops are Celery tasks in `plane/app/orchestrator/loop_tasks.py` that call `_run_loop(workspace_id, headline, instructions)`. The headline and instructions become the PM agent's prompt, followed by the standard operating rules.

1. Add a `@shared_task` that calls `_run_loop` with a focused brief that names the tools to use.
2. Export it from `plane/app/tasks.py` so the Celery worker registers it.
3. Add an entry to `app.conf.beat_schedule` in `plane/celery.py`.

## Change scheduling policy

`SchedulingEngine` in `plane/app/schedules/engine.py` is the one place that decides whether and how hard to dispatch. `_calculate_intensity_with_runway()` maps budget utilization and runway to `skip`, `conservative`, `normal` or `aggressive`, and `Orchestrator.compose_dispatch_prompt()` in `plane/app/orchestrator/engine.py` turns that intensity into prompt instructions. Every evaluation is logged to `SchedulingDecision`, so a policy change can be checked against the decisions it would have made.

## Tests

- Relay: `pnpm --filter cyrus-relay test` (Node's built-in test runner) and `pnpm --filter cyrus-relay check:types`.
- API: the orchestration tests live in `cyrus/apps/api/plane/tests/unit/test_cyrus_phase2.py`, `test_cyrus_phase3.py`, `test_dashboard_metrics.py`, `test_lifecycle.py` and `plane/tests/contract/api/test_cyrus_phase1.py`. They use Plane's pytest-django setup and need Postgres and Redis running. CI runs them on every push (98 tests). Locally, from `cyrus/apps/api` with `AMQP_URL=memory://` and `WEB_URL=http://localhost:3000` set: `pytest plane/tests/unit/test_lifecycle.py plane/tests/unit/test_cyrus_phase2.py plane/tests/unit/test_cyrus_phase3.py plane/tests/unit/test_dashboard_metrics.py plane/tests/contract/api/test_cyrus_phase1.py`.
- Web: `cd cyrus/apps/web && pnpm exec vitest run` runs the Vitest suite, including the schedule overlap validation tests.
