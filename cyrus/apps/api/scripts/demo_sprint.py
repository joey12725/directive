#!/usr/bin/env python
"""
End-to-End Test: Cyrus Orchestrator → Snake Game Sprint
=========================================================

Cyrus (the PM agent) receives a project idea, lays out the work in the
Plane backend, then autonomously delegates 3 stories to Gemini CLI worker
agents and reports when the sprint is complete.

Architecture:
  Test script → ACPXDispatcher → relay /dispatch
                → Gemini CLI (running AS Cyrus)
                    → cyrus_tool start_story_session (story 1)
                        → relay /dispatch → Gemini CLI (worker)
                    → cyrus_tool start_story_session (story 2) …
                    → cyrus_tool start_story_session (story 3) …
                    → reports sprint done

Run inside the Django API container:
  docker exec -e DEMO_WORKSPACE_PATH=/path/on/relay/host cyrus-api-1 python scripts/demo_sprint.py
"""
import os
import sys
import time
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from django.utils import timezone
from plane.db.models import (
    Agent, AgentStatus,
    ComputePool, Issue, Project, State, Workspace,
    CyrusSession, SessionStatus, WorkspaceMember,
)
from plane.db.models.state import StateGroup
from plane.app.agents.dispatcher import ACPXDispatcher

# agent_type string literals (from Agent field choices)
AGENT_TYPE_GEMINI = "gemini"

# ─────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────
RELAY_URL       = os.environ.get("CYRUS_RELAY_URL", "http://host.docker.internal:7420")
RELAY_SECRET    = os.environ.get("CYRUS_RELAY_SECRET", "")
WORKSPACE_PATH  = os.environ.get("DEMO_WORKSPACE_PATH", os.path.expanduser("~/snake-game2"))
PROJECT_NAME    = "Snake Game 2"
PROJECT_IDENT   = "SNKV2"

SOUL_MD = """\
# Cyrus Agent

You are Cyrus, the Autonomous Product Manager.

## Identity
- You are proactive, efficient, and delegatory.
- You unblock worker agents automatically whenever safe to do so.
- You synthesize execution context into durable docs, wiki pages, and work items.
- You only escalate to the human CEO when a decision is materially ambiguous, risky, or externally blocked.
- You rely on the `cyrus_tool` command for all backend reads and writes.

## Operating Style
- Prefer finishing the next useful action over narrating intent.
- Default to structured delegation: route implementation to specialists.
- Preserve token discipline: check budget and pool health before dispatching.
- Every dispatch must leave enough traceability for later synthesis.

## Tool Interface
Run backend operations with:
  cyrus_tool <tool_name> <json_args>

Examples:
  cyrus_tool get_markdown_view '{"project_id":"<id>"}'
  cyrus_tool start_story_session '{"work_item_id":"<id>","agent_id":"<worker_id>","workspace_id":"<ws_id>","prompt":"<text>"}'
  cyrus_tool update_work_item '{"issue_id":"<id>","state_group":"completed"}'

IMPORTANT: cyrus_tool calls are BLOCKING. They wait until the worker finishes.
Do NOT dispatch the next story until the current one returns.
"""


def sep(label):
    print(f"\n{'='*60}\n  {label}\n{'='*60}")


def ok(label, detail=""):
    print(f"  ✓  {label}" + (f"  — {detail}" if detail else ""))


def fail(label, detail=""):
    print(f"  ✗  {label}" + (f"  — {detail}" if detail else ""))
    raise SystemExit(f"\nFATAL: {label}")


# ─────────────────────────────────────────────────────────
# Phase 0 – Prerequisites
# ─────────────────────────────────────────────────────────
sep("PHASE 0 — Prerequisites")

import urllib.request
try:
    resp = urllib.request.urlopen(f"{RELAY_URL}/health", timeout=5)
    health = json.loads(resp.read())
    ok("Relay healthy", str(health.get("status")))
except Exception as e:
    fail("Relay health", str(e))

ws = Workspace.objects.filter(deleted_at__isnull=True).first()
ok("Workspace", ws.name)

member = WorkspaceMember.objects.filter(
    workspace=ws, role__gte=10, deleted_at__isnull=True
).select_related("member").first()
ok("Workspace member", member.member.email)
user = member.member

# ─────────────────────────────────────────────────────────
# Phase 1 – Fix Cyrus PM agent + Gemini worker agent
# ─────────────────────────────────────────────────────────
sep("PHASE 1 — Agent Setup")

pool = ComputePool.objects.filter(workspace=ws, deleted_at__isnull=True).first()
ok("Pool", f"{pool.name} ({pool.id})")

if pool.budget_limit_usd is None or pool.budget_limit_usd < 50:
    pool.budget_limit_usd = 50.0
    pool.save(update_fields=["budget_limit_usd", "updated_at"])
    print("     → Set pool budget = $50")

# Fix the Cyrus PM orchestrator agent
cyrus_agent = Agent.objects.filter(
    workspace=ws, is_cyrus_agent=True, deleted_at__isnull=True
).first()

if cyrus_agent is None:
    cyrus_agent = Agent(
        workspace=ws,
        name="Cyrus PM",
        is_cyrus_agent=True,
        pool=pool,
    )

cyrus_agent.agent_type  = AGENT_TYPE_GEMINI
cyrus_agent.relay_url   = RELAY_URL
cyrus_agent.relay_secret = RELAY_SECRET
cyrus_agent.acpx_agent_name = "gemini"
cyrus_agent.status      = AgentStatus.ONLINE
cyrus_agent.config      = {
    "model": "gemini-2.5-pro",
    "timeout_seconds": 7200,   # 2 hours – Cyrus orchestrates multiple stories
}
cyrus_agent.save()
ok("Cyrus PM agent", f"id={cyrus_agent.id}  acpx=gemini  timeout=7200s")

# Gemini worker agent (executes individual stories)
worker_agent, created = Agent.objects.update_or_create(
    workspace=ws,
    name="Gemini Worker",
    defaults={
        "agent_type": AGENT_TYPE_GEMINI,
        "is_cyrus_agent": False,
        "relay_url": RELAY_URL,
        "relay_secret": RELAY_SECRET,
        "acpx_agent_name": "gemini",
        "pool": pool,
        "status": AgentStatus.ONLINE,
        "config": {
            "model": "gemini-2.5-pro",
            "timeout_seconds": 1800,  # 30 min per story
        },
    },
)
ok(f"{'Created' if created else 'Updated'} Gemini worker", f"id={worker_agent.id}")

# ─────────────────────────────────────────────────────────
# Phase 2 – Create fresh project + stories
# ─────────────────────────────────────────────────────────
sep("PHASE 2 — Project & Stories")

# Clean up previous run
old = Project.objects.filter(workspace=ws, identifier=PROJECT_IDENT, deleted_at__isnull=True).first()
if old:
    Issue.objects.filter(project=old).update(deleted_at=timezone.now())
    old.deleted_at = timezone.now()
    old.save(update_fields=["deleted_at"])
    print(f"     Cleaned up previous project {old.id}")

project = Project.objects.create(
    workspace=ws,
    name=PROJECT_NAME,
    identifier=PROJECT_IDENT,
    description="Snake game sprint orchestrated by Cyrus",
    workspace_path=WORKSPACE_PATH,
    cycle_duration="5h",
    created_by=user,
    updated_by=user,
)
ok("Project created", f"{project.identifier} ({project.id})")

states = {}
for group, name, color, seq in [
    (StateGroup.BACKLOG.value,    "Backlog",     "#94a3b8", 1),
    (StateGroup.STARTED.value,    "In Progress", "#f59e0b", 2),
    (StateGroup.COMPLETED.value,  "Done",        "#10b981", 3),
]:
    states[group] = State.objects.create(
        project=project, workspace=ws, name=name, group=group,
        color=color, sequence=seq, created_by=user, updated_by=user,
    )
ok("States", "Backlog / In Progress / Done")

STORY_SPECS = [
    {
        "name": "Ideation: Design snake game architecture",
        "description": (
            f"Design the architecture for a Python terminal snake game.\n\n"
            f"Deliverable: write DESIGN.md to {WORKSPACE_PATH} covering:\n"
            f"- Game loop, data structures, controls, rendering (use curses stdlib)\n"
            f"- File layout for the implementation\n"
            f"- How to run and test the game\n\n"
            f"Output one file only: DESIGN.md"
        ),
    },
    {
        "name": "Development: Implement snake game in Python",
        "description": (
            f"Implement a fully functional terminal snake game in Python.\n\n"
            f"Workspace: {WORKSPACE_PATH}\n"
            f"- Read DESIGN.md if present for guidance\n"
            f"- Use the curses module (no external dependencies)\n"
            f"- Snake grows when eating food\n"
            f"- Game over on wall or self collision\n"
            f"- Score displayed on screen\n"
            f"- Save as snake.py + README.md in {WORKSPACE_PATH}"
        ),
    },
    {
        "name": "Validation: Test and verify snake game",
        "description": (
            f"Validate the snake game implementation in {WORKSPACE_PATH}.\n\n"
            f"Tasks:\n"
            f"- Confirm snake.py exists and passes: python -m py_compile snake.py\n"
            f"- Review code for all required mechanics (movement, growth, food, collision, score)\n"
            f"- Write VALIDATION.md summarising findings and ship/no-ship verdict\n"
        ),
    },
]

stories = []
for i, spec in enumerate(STORY_SPECS, 1):
    issue = Issue.objects.create(
        project=project,
        workspace=ws,
        name=spec["name"],
        description_stripped=spec["description"],
        state=states[StateGroup.BACKLOG.value],
        priority="high",
        created_by=user,
        updated_by=user,
    )
    stories.append(issue)
    ok(f"Story {i}", f"[{issue.id}] {issue.name[:55]}")

# ─────────────────────────────────────────────────────────
# Phase 3 – Build the Cyrus orchestrator prompt
# ─────────────────────────────────────────────────────────
sep("PHASE 3 — Build Cyrus Prompt")

story_block = "\n".join([
    f"{i+1}. ID={s.id}\n"
    f"   Name: {s.name}\n"
    f"   Description: {s.description_stripped[:300].strip()}\n"
    for i, s in enumerate(stories)
])

cyrus_prompt = f"""\
{SOUL_MD}

---

## Sprint Mission: Snake Game

You have been activated to orchestrate a Snake Game development sprint from scratch.

### Context
- Workspace ID   : {ws.id}
- Project ID     : {project.id}
- Project        : {project.identifier} — {project.name}
- Workspace path : {WORKSPACE_PATH}
- Worker agent   : {worker_agent.id}  (Gemini CLI — executes code stories)

### Your Job
1. Review the project backlog (optional but good practice)
2. Execute all 3 stories **in order**, one at a time
3. Report the final status of each story when done

### Stories to Execute (in this exact order)
{story_block}

### How to Dispatch a Story
Use this command to delegate a story to the Gemini worker agent:

  cyrus_tool start_story_session '{{"work_item_id":"<STORY_ID>","agent_id":"{worker_agent.id}","workspace_id":"{ws.id}","prompt":"<FULL STORY PROMPT>"}}'

The call BLOCKS until the worker completes. Only dispatch the next story after the previous one returns.

### Story Prompts to Use

**Story 1 prompt (ideation):**
"Design the architecture for a Python terminal snake game using the curses stdlib. Write DESIGN.md to {WORKSPACE_PATH} covering: game loop, data structures, controls, rendering approach, file layout. No code needed — design document only."

**Story 2 prompt (development):**
"Implement a complete terminal snake game in Python using curses (stdlib only). Workspace: {WORKSPACE_PATH}. Read DESIGN.md if present. Requirements: snake grows on food, game over on wall/self collision, score display, arrow key controls. Save as snake.py + README.md. Run: python -m py_compile snake.py to verify syntax."

**Story 3 prompt (validation):**
"Validate the snake game in {WORKSPACE_PATH}. Steps: (1) confirm snake.py exists, (2) run python -m py_compile snake.py and report result, (3) review code for movement/growth/food/collision/score mechanics, (4) write VALIDATION.md with findings and a clear SHIP / NO-SHIP verdict."

### Mandatory Rules
- Use `cyrus_tool` for all backend operations (not Python scripts or HTTP calls)
- Dispatch stories ONE AT A TIME in order — wait for each to complete before starting the next
- Do not skip any story
- After all 3 stories complete, print a final summary: which stories passed/failed and the overall sprint verdict
"""

print(f"\n  Prompt length: {len(cyrus_prompt)} chars")
print(f"  Preview:\n  " + cyrus_prompt[:200].replace("\n", "\n  ") + "...")

# ─────────────────────────────────────────────────────────
# Phase 4 – Dispatch Cyrus and watch the sprint run
# ─────────────────────────────────────────────────────────
sep("PHASE 4 — Cyrus Dispatch")

print(f"\n  Dispatching Cyrus PM agent…")
print(f"  Agent  : {cyrus_agent.name} ({cyrus_agent.id})")
print(f"  Backend: Gemini CLI via {RELAY_URL}")
print(f"  Timeout: {cyrus_agent.config['timeout_seconds']}s")
print(f"  CWD    : {WORKSPACE_PATH}\n")

t0 = time.time()

try:
    dispatcher = ACPXDispatcher(
        agent=cyrus_agent,
        pool=pool,
        project=project,
        work_item=stories[0],   # Cyrus's own session is anchored to story 1
        goal=None,
    )
    cyrus_session = dispatcher.dispatch(cyrus_prompt)
    elapsed = time.time() - t0

    print(f"\n  ── Cyrus Session Result {'─'*38}")
    print(f"  Session ID : {cyrus_session.id}")
    print(f"  Status     : {cyrus_session.status}")
    print(f"  Duration   : {elapsed:.1f}s")
    print(f"  Tokens     : {cyrus_session.total_tokens or 0}")
    print(f"  Model      : {cyrus_session.model_name or 'unknown'}")

    # Print the last chunk of Cyrus's output
    event_log = cyrus_session.event_log or []
    chunks = [e for e in event_log if e.get("type") == "agent_message_chunk"]
    if chunks:
        last = chunks[-1].get("text", "")
        print(f"\n  Cyrus final output ({len(last)} chars):")
        print("  " + last[-1500:].replace("\n", "\n  "))

    errors = [e for e in event_log if e.get("type") in ("relay_error", "relay_exit") and e.get("code", 0) != 0]
    for err in errors:
        print(f"\n  ⚠ Error event: {err}")

except Exception as exc:
    import traceback
    print(f"\n  ✗ Exception: {exc}")
    traceback.print_exc()

# ─────────────────────────────────────────────────────────
# Phase 5 – Final story state report
# ─────────────────────────────────────────────────────────
sep("PHASE 5 — Sprint Report")

all_done = True
for i, story in enumerate(stories, 1):
    story.refresh_from_db()
    state_name = story.state.name if story.state_id else "unknown"
    group = story.state.group if story.state_id else "?"
    done = group == StateGroup.COMPLETED.value
    sym = "✓" if done else "✗"
    print(f"  {sym}  Story {i}: {story.name[:55]}")
    print(f"       State: {state_name}  group={group}")
    if not done:
        all_done = False

# Also report how many CyrusSessions were created (Cyrus + workers)
sessions = CyrusSession.objects.filter(project=project).select_related("agent")
print(f"\n  Sessions recorded: {sessions.count()}")
for s in sessions:
    print(f"    [{s.agent.name}] status={s.status}  tokens={s.total_tokens}  cost=${s.estimated_cost_usd or 0:.4f}")

print()
if all_done:
    print("  ✓ ALL 3 STORIES DONE — Sprint PASSED!")
else:
    print("  ✗ Sprint incomplete — check output above for errors")
print()
