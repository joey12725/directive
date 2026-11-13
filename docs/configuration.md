# Configuration

Directive uses Plane's configuration for everything Plane already does (database, Redis, RabbitMQ, object storage, auth, email). `cyrus/setup.sh` copies every `.env.example` to `.env` and generates a Django `SECRET_KEY`. This page covers the settings the orchestration layer adds.

## API service (`cyrus/apps/api/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `CYRUS_DEFAULT_WORKSPACE_ID` | empty | Workspace the autonomous loops run against. Leave empty to run them for every workspace that has a PM agent. |
| `CYRUS_WIKI_ROOT` | `<repo>/wiki` | Folder of markdown notes the archivist loop mirrors into workspace pages. |
| `CYRUS_APPRISE_WEBHOOK` or `APPRISE_WEBHOOK_URL` | empty | Optional [Apprise](https://github.com/caronc/apprise) endpoint for push notifications when an agent escalates to a human. |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | `openai`, empty, `gpt-4o-mini` | Model used by the in-app AI helpers. |

## Celery Beat

Beat uses `django_celery_beat`'s database scheduler, and the static schedule in `cyrus/apps/api/plane/celery.py` is loaded into it on start.

| Entry | Task | Cadence |
|---|---|---|
| `cyrus-scheduling-tick` | `plane.app.schedules.tasks.scheduling_tick` | every 5 min |
| `cyrus-agent-health-check` | `plane.app.agents.tasks.check_agent_health` | every 5 min |
| `cyrus-visionary-ideation-loop` | `plane.app.orchestrator.loop_tasks.visionary_ideation_loop` | every 30 min |
| `cyrus-backlog-grooming-loop` | `plane.app.orchestrator.loop_tasks.backlog_grooming_loop` | every 2 h |
| `cyrus-janitor-triage-loop` | `plane.app.orchestrator.loop_tasks.janitor_triage_loop` | every 4 h |
| `cyrus-alignment-audit-loop` | `plane.app.orchestrator.loop_tasks.audit_alignment_loop` | daily, 08:00 UTC |
| `cyrus-archivist-wiki-loop` | `plane.app.wiki_sync.tasks.archivist_wiki_loop` | every 6 h |

To pause a loop without a code change, disable its row in Django admin or from a shell:

```bash
docker exec -it cyrus-api-1 python manage.py shell -c \
  "from django_celery_beat.models import PeriodicTask; PeriodicTask.objects.filter(name='cyrus-visionary-ideation-loop').update(enabled=False)"
```

`manage_cycles` (rolls each project's 5h, 24h or 7d cycle forward) is registered as a task but is not on the default schedule. Add it to Beat if you want cycles created automatically.

## Relay (`cyrus/relay/.env.example`)

The relay reads plain environment variables. Run it on the machine where the agent CLIs are installed and signed in.

| Variable | Default | Purpose |
|---|---|---|
| `CYRUS_RELAY_PORT` | `7420` | Listen port. |
| `CYRUS_RELAY_SECRET` | empty | Bearer token the API must send. Always set this outside local testing. |
| `CYRUS_RELAY_DEFAULT_CWD` | home directory | Working directory when a request does not name one. |
| `CYRUS_RELAY_AGENT_LIST` | `codex,claude,gemini,openclaw,opencode` | Agents this relay advertises on `/agents`. |
| `CYRUS_CLAUDE_BINARY` | `claude` | Path to the Claude Code CLI if it is not on `PATH`. |
| `CYRUS_CODEX_MODEL`, `CYRUS_OPENCODE_MODEL` | CLI default | Model label recorded on sessions for those CLIs. |
| `CYRUS_OPENCLAW_SESSION_KEY` | `agent:main:main` | OpenClaw session key to run prompts in. |
| `CYRUS_OPENCLAW_DIST_DIR`, `OPENCLAW_CONFIG_PATH` | auto-detected | Where to find an OpenClaw install and its config. |

The relay is meant for a private network. Put it behind a VPN or tunnel rather than exposing it to the internet, and keep the secret set.

## Registering agents and pools

Pools, agents, schedules and allocations are workspace-scoped resources on the public API (`/api/v1/workspaces/<slug>/...`, authenticated with a personal access token in `X-Api-Key`):

| Resource | Path |
|---|---|
| Compute pools | `compute-pools/` |
| Agents | `agents/` |
| Schedules and rows | `schedules/`, `schedule-rows/` |
| Allocations | `compute-allocations/` |
| Goals and KPIs | `goals/`, `goal-kpis/` |
| Sessions, approvals | `sessions/`, `approvals/` |
| Model tiers | `model-tier-configs/` |

An agent needs `relay_url` (for example `http://host.docker.internal:7420`), `relay_secret`, `acpx_agent_name` (the relay agent name such as `claude`, `codex` or `gemini`), `agent_type` and a `pool`. Set `is_cyrus_agent: true` on exactly one agent per workspace to make it the PM agent.

Each project the scheduler should work on needs a `workspace_path`, the directory on the relay machine where the agent will run.

The scripts in `cyrus/apps/api/scripts/` do this setup for you in a development stack:

| Script | What it does |
|---|---|
| `demo_sprint.py` | Registers a PM agent and a Gemini worker, creates a demo project, and lets the PM agent plan and delegate a three-story sprint. |
| `demo_single_project.py` | Same demo without the PM agent: dispatches three stories directly. |
| `create_cyrus_agent.py` | Creates or updates a PM agent bound to an existing Anthropic pool. |
| `setup_beat_tasks.py` | Re-creates the loop entries in the Beat database, for stacks that started before the loops existed. |

Run them inside the API container, for example `docker exec cyrus-api-1 python scripts/demo_sprint.py`.
