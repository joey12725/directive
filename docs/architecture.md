# Architecture

Directive has three moving parts:

1. **The project-management layer**, a fork of Plane v1.2.3. It owns workspaces, projects, work items, states, cycles, modules, pages and comments.
2. **The orchestration layer**, a set of Django apps and Celery tasks inside the same API service. It owns goals, agents, compute pools, schedules, sessions and every decision about what runs next.
3. **The Cyrus Relay**, a Fastify process that runs on whichever machine has the coding-agent CLIs installed and logged in. It turns HTTP requests into CLI runs and streams normalized events back.

All new backend code lives in its own Django apps under `cyrus/apps/api/plane/app/` and its own tables (prefixed `cyrus_`), so the fork boundary is easy to see.

## Data model

Defined in `cyrus/apps/api/plane/db/models/cyrus.py`, plus three fields added to Plane's `Project`: `goal`, `workspace_path` (where the agent works on the relay machine) and `cycle_duration`.

| Model | Role |
|---|---|
| `Goal`, `GoalKPI` | Open-ended objectives with named metrics and time-series datapoints. Projects link to a goal. |
| `ComputePool` | A source of compute: a `subscription` (rate-limited, flat rate) or `api_billing` (USD budget per day, week or month), with provider, per-token costs and configured rate limits. |
| `Agent` | A registered worker or the PM agent (`is_cyrus_agent`). Holds its relay URL, relay secret, CLI name, pool, status and last heartbeat. |
| `PoolUsageRecord` | One row of metered usage per session: input, output, cache and reasoning tokens plus cost. |
| `RateLimitEvent` | Every 429 seen from a provider, with the request and token counts at the time and the retry-after hint. |
| `Schedule`, `ScheduleRow`, `ScheduleTemplate` | Weekly time windows that say when compute may be spent. |
| `ComputeAllocation` | Binds a pool to a project or goal with a priority, cooldown and failure counter. This is what the scheduler iterates. |
| `CyrusSession` | One agent run: the full event log, usage, cost, outcome and summary, linked to its agent, pool, project, goal and work item. |
| `Approval` | A request for a human decision, raised by an agent. |
| `ModelTierConfig` | High, medium and low effort model choices per workspace. |
| `SchedulingDecision` | An audit row for every scheduling evaluation, including skipped ones and why. |

## Dispatch path

1. **Celery Beat** fires `plane.app.schedules.tasks.scheduling_tick`.
2. `SchedulingEngine.compute_dispatch_plan()` runs per workspace under a cache lock. It loads active allocations for the current time window, sorts them by effective priority, and drops any that are in cooldown, behind an open circuit breaker (too many consecutive failures) or already running a session.
3. For each survivor it reads cached pool state from `BudgetService` and picks an intensity:
   - `skip` above 95% budget utilization
   - `conservative` above 85% utilization or with under three days of runway at the current burn rate
   - `aggressive` for priority 1 to 2 work under 50% utilization
   - `normal` otherwise

   Each evaluation is written to `SchedulingDecision`.
4. `execute_dispatch(allocation_id, intensity)` picks the next actionable work item, composes the prompt (the intensity changes the instructions), and hands it to `ACPXDispatcher`.
5. `ACPXDispatcher` creates a `CyrusSession`, runs `WorkItemLifecycle.start()` on the work item, and POSTs to the agent's relay at `/dispatch` with a bearer token. The timeout comes from agent config, then pool config, then a 600-second default.
6. The relay spawns the CLI in the project's `workspace_path`, parses its output and streams NDJSON events back.
7. The dispatcher appends every event to the session's event log. On the final `done` event it records usage through `ComputeTracker`, which writes a `PoolUsageRecord`. A 429 becomes a `RateLimitEvent`. A connection error marks the agent offline.
8. On completion, `WorkItemLifecycle.complete()` moves the item to Done, fills in derivable fields, and a summary comment is posted on the work item.

## The PM agent

The PM agent is an ordinary `Agent` row with `is_cyrus_agent=True`. It is dispatched through the same relay as any worker. What makes it different is the prompt and the toolset: it is told to use `python manage.py cyrus_tool <tool> '<json>'` for every backend read and write. The tools live in `plane/app/orchestrator/tools.py` in a single `TOOL_REGISTRY` and cover planning, backlog management, execution, reporting and escalation.

`start_story_session` is the core of delegation. It dispatches a worker, then sends the same worker a short evaluation prompt asking for `DONE: <summary>` or `INCOMPLETE: <gaps>`. An incomplete verdict turns into a continuation prompt that lists the gaps and restates the requirements. After `max_passes` (default 3) the story is either closed or left open with a spike for the PM agent to reroute.

The autonomous loops in `plane/app/orchestrator/loop_tasks.py` are Celery tasks that dispatch the PM agent with a specific brief: ideation, backlog grooming, janitor triage and alignment audit. `plane/app/wiki_sync/tasks.py` adds an archivist loop that mirrors a folder of markdown notes into workspace pages.

## Work-item lifecycle

`plane/app/orchestrator/lifecycle.py` is the single gate for state transitions made by agents. On start it sets the assignee, start date and an in-progress state. On completion it sets the completed state and timestamp and makes sure a session summary comment exists. It returns a `ComplianceReport` listing what it fixed and any violations. Error-level violations block the transition, warnings are logged. Any new dispatch path that goes through this class gets the same completeness rules for free.

## Rate-limit learning

`PoolRateModel` (`plane/app/metering/rate_model.py`) combines a pool's configured request and token limits with the lowest counts observed at the moment of a 429. Over time the effective throughput estimate converges on what the provider really allows, and `BudgetService.can_dispatch()` uses it, together with budget state, to say whether a dispatch should go ahead and why.

## Frontend

New views live in `cyrus/apps/web`:

- **Executive dashboard** (`core/components/dashboard`): metric cards, goal KPI cards, pool cost tracker, active blockers, alignment-drift panel and an activity summary.
- **Goals** (`core/components/goals`): goal detail with KPI history charts and forms.
- **Sessions** (`core/components/sessions`): a replay viewer that renders each event type in a timeline next to session metadata.
- **Schedules** (`core/components/schedules`): a weekly schedule editor with overlap validation.
- **Agents, pools and sessions lists** (`core/components/cyrus-lists`).

They talk to the API through `core/services/cyrus-crud.service.ts`, `cyrus-dashboard.service.ts` and `session.service.ts`.
