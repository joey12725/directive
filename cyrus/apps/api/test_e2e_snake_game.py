#!/usr/bin/env python
"""
End-to-End Test: Snake Game Sprint via Orchestrator
====================================================

Tests the full orchestration pipeline:
  Story 1 → Gemini CLI (ideation)
  Story 2 → Gemini CLI (development)
  Story 3 → Gemini CLI (validation)

Run inside the Django API container:
  docker exec cyrus-api-1 python test_e2e_snake_game.py
"""
import os
import sys
import time
import traceback

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plane.settings.production")
sys.path.insert(0, os.path.dirname(__file__))

import django
django.setup()

from django.utils import timezone
from plane.db.models import (
    Agent, AgentStatus, ComputePool,
    Issue, Project, State, Workspace,
    CyrusSession, SessionStatus,
)
from plane.db.models.state import StateGroup
from plane.app.agents.dispatcher import ACPXDispatcher
from plane.app.orchestrator.engine import Orchestrator

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
RELAY_URL     = "http://host.docker.internal:7420"
RELAY_SECRET  = "dev-secret"
# The snake game workspace dir lives on the HOST (relay's filesystem)
WORKSPACE_PATH = r"C:\Users\you\snake-game"

SPRINT_NAME = "Snake Game Sprint"
PROJECT_NAME = "Snake Game"
PROJECT_IDENTIFIER = "SNAKE"


def sep(label: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print('='*60)


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "✓" if ok else "✗"
    print(f"  {status}  {label}", end="")
    if detail:
        print(f"  — {detail}", end="")
    print()
    if not ok:
        raise SystemExit(f"\nFATAL: {label} failed. {detail}")


# ─────────────────────────────────────────────
# Phase 0: Prerequisites
# ─────────────────────────────────────────────
sep("PHASE 0 — Prerequisites")

import urllib.request, json

try:
    resp = urllib.request.urlopen(f"{RELAY_URL}/health", timeout=5)
    health = json.loads(resp.read().decode())
    check("Relay health", health.get("status") == "ok", str(health))
except Exception as e:
    check("Relay health", False, str(e))

ws = Workspace.objects.filter(deleted_at__isnull=True).first()
check("Workspace exists", ws is not None, str(ws))
print(f"     Workspace: {ws.name} ({ws.id})")


# ─────────────────────────────────────────────
# Phase 1: Set up agents
# ─────────────────────────────────────────────
sep("PHASE 1 — Agent Setup")

# Fetch or create a pool for these agents
pool = ComputePool.objects.filter(
    workspace=ws,
    provider="anthropic",
    deleted_at__isnull=True,
).first()

if pool is None:
    pool = ComputePool.objects.filter(workspace=ws, deleted_at__isnull=True).first()

check("Compute pool exists", pool is not None, str(pool))
print(f"     Pool: {pool.name} ({pool.id})  type={pool.pool_type}")

# Ensure budget_limit_usd is generous for the sprint
if pool.budget_limit_usd is None or pool.budget_limit_usd < 50:
    pool.budget_limit_usd = 50.0
    pool.save(update_fields=["budget_limit_usd", "updated_at"])
    print("     → Set pool budget_limit_usd = $50")

# Gemini CLI execution agent (all three stories)
gemini_agent, created = Agent.objects.update_or_create(
    workspace=ws,
    name="Gemini Story Agent",
    defaults={
        "agent_type": "gemini",
        "is_cyrus_agent": False,
        "relay_url": RELAY_URL,
        "relay_secret": RELAY_SECRET,
        "acpx_agent_name": "gemini",
        "pool": pool,
        "status": AgentStatus.ONLINE,
        "config": {"model": "gemini-2.5-pro"},
    },
)
print(f"     {'Created' if created else 'Updated'} Gemini agent: {gemini_agent.name} ({gemini_agent.id})")


# ─────────────────────────────────────────────
# Phase 2: Create project
# ─────────────────────────────────────────────
sep("PHASE 2 — Project Creation")

# Get any workspace user to use as creator
from plane.db.models import WorkspaceMember
member = WorkspaceMember.objects.filter(
    workspace=ws,
    role__gte=10,  # member or above
    deleted_at__isnull=True,
).select_related("member").first()
check("At least one workspace member exists", member is not None)
user = member.member
print(f"     Using user: {user.email} ({user.id})")

# Clean up previous test run if project exists
old_project = Project.objects.filter(
    workspace=ws,
    name=PROJECT_NAME,
    deleted_at__isnull=True,
).first()
if old_project:
    print(f"     Cleaning up previous project: {old_project.id}")
    # Soft-delete issues
    Issue.objects.filter(project=old_project).update(deleted_at=timezone.now())
    # Soft-delete the project
    old_project.deleted_at = timezone.now()
    old_project.save(update_fields=["deleted_at"])

# Create project
project = Project.objects.create(
    workspace=ws,
    name=PROJECT_NAME,
    identifier=PROJECT_IDENTIFIER,
    description="Snake game developed by the Cyrus orchestrator e2e test",
    workspace_path=WORKSPACE_PATH,
    cycle_duration="5h",
    created_by=user,
    updated_by=user,
)
print(f"     ✓ Project created: {project.name} ({project.id})")
print(f"       identifier={project.identifier}  workspace_path={project.workspace_path}")


# ─────────────────────────────────────────────
# Phase 3: Create states
# ─────────────────────────────────────────────
sep("PHASE 3 — Workflow States")

states = {
    StateGroup.BACKLOG.value: State.objects.create(
        project=project, workspace=ws,
        name="Backlog", group=StateGroup.BACKLOG.value,
        color="#94a3b8", sequence=1,
        created_by=user, updated_by=user,
    ),
    StateGroup.STARTED.value: State.objects.create(
        project=project, workspace=ws,
        name="In Progress", group=StateGroup.STARTED.value,
        color="#f59e0b", sequence=2,
        created_by=user, updated_by=user,
    ),
    StateGroup.COMPLETED.value: State.objects.create(
        project=project, workspace=ws,
        name="Done", group=StateGroup.COMPLETED.value,
        color="#10b981", sequence=3,
        created_by=user, updated_by=user,
    ),
}
print(f"     ✓ Created {len(states)} workflow states: Backlog, In Progress, Done")


# ─────────────────────────────────────────────
# Phase 4: Create stories
# ─────────────────────────────────────────────
sep("PHASE 4 — Story Creation")

backlog_state = states[StateGroup.BACKLOG.value]
done_state = states[StateGroup.COMPLETED.value]

stories = [
    {
        "name": "Ideation: Design the snake game architecture",
        "description": (
            "Brainstorm and design the architecture for a Python snake game. Define:\n"
            "- Core game loop mechanics\n"
            "- Data structures (snake body, food, grid)\n"
            "- Controls and rendering approach\n"
            "- Python library choices (pygame, curses, or pure terminal)\n"
            "- File structure for the implementation\n\n"
            f"Output a concise design document as DESIGN.md in the workspace directory: {WORKSPACE_PATH}"
        ),
        "agent": gemini_agent,
        "agent_label": "Gemini CLI",
    },
    {
        "name": "Development: Implement the snake game in Python",
        "description": (
            f"Implement a fully functional snake game in Python. Workspace directory: {WORKSPACE_PATH}\n\n"
            "Requirements:\n"
            "- Read DESIGN.md from the workspace directory for architecture guidance (if it exists)\n"
            "- Implement a working snake game using the curses module (standard library only)\n"
            "- The snake should grow when eating food\n"
            "- Game over when hitting wall or self\n"
            "- Score tracking displayed on screen\n"
            f"- Save the complete game as snake.py in {WORKSPACE_PATH}\n"
            f"- Include a README.md with instructions to run the game in {WORKSPACE_PATH}"
        ),
        "agent": gemini_agent,
        "agent_label": "Gemini CLI",
    },
    {
        "name": "Validation: Test and validate the snake game",
        "description": (
            f"Test and validate the snake game implementation in workspace: {WORKSPACE_PATH}\n\n"
            "Tasks:\n"
            f"- Check that snake.py exists in {WORKSPACE_PATH}\n"
            "- Review the code for correctness and completeness\n"
            "- Verify that all core mechanics are implemented (movement, growth, food, collision, score)\n"
            f"- Run syntax check: python -m py_compile {WORKSPACE_PATH}/snake.py\n"
            f"- Write a brief validation report as VALIDATION.md in {WORKSPACE_PATH}\n"
            "- Report any bugs found and state whether the game is ready to ship"
        ),
        "agent": gemini_agent,
        "agent_label": "Gemini CLI",
    },
]

created_stories = []
for i, story_data in enumerate(stories, start=1):
    issue = Issue.objects.create(
        project=project,
        workspace=ws,
        name=story_data["name"],
        description_stripped=story_data["description"],
        state=backlog_state,
        priority="high",
        created_by=user,
        updated_by=user,
    )
    story_data["issue"] = issue
    created_stories.append(story_data)
    print(f"     ✓ Story {i}: [{story_data['agent_label']}] {issue.name[:60]}")
    print(f"              ID: {issue.id}")

print(f"\n     Total stories created: {len(created_stories)}")


# ─────────────────────────────────────────────
# Phase 5: Sprint execution
# ─────────────────────────────────────────────
sep("PHASE 5 — Sprint Execution (3 stories)")

orchestrator = Orchestrator()
results = []

for story_num, story_data in enumerate(created_stories, start=1):
    issue = story_data["issue"]
    agent = story_data["agent"]
    agent_label = story_data["agent_label"]

    print(f"\n  ┌─ Story {story_num}/3 ─────────────────────────────────────────┐")
    print(f"  │  Agent:  {agent_label}")
    print(f"  │  Story:  {issue.name[:55]}")
    print(f"  └────────────────────────────────────────────────────────────┘")

    # Compose prompt via orchestrator
    prompt = orchestrator.compose_dispatch_prompt(issue, intensity="normal")
    print(f"\n  Prompt preview ({len(prompt)} chars):")
    print("  " + prompt[:200].replace("\n", "\n  ") + "...")

    # Dispatch
    print(f"\n  Dispatching to {agent_label} via relay...")
    t0 = time.time()

    try:
        dispatcher = ACPXDispatcher(
            agent=agent,
            pool=pool,
            project=project,
            work_item=issue,
            goal=None,
        )
        session = dispatcher.dispatch(prompt)
        elapsed = time.time() - t0

        status_label = session.status
        tokens = session.total_tokens or 0
        cost = float(session.estimated_cost_usd or 0)

        print(f"\n  ── Session Result ──────────────────────────────────────────")
        print(f"  Session ID  : {session.id}")
        print(f"  Status      : {status_label}")
        print(f"  Duration    : {elapsed:.1f}s")
        print(f"  Tokens      : {tokens}")
        print(f"  Cost        : ${cost:.4f}")
        print(f"  Model       : {session.model_name or 'unknown'}")

        # Show last assistant message chunk
        event_log = session.event_log or []
        chunks = [e for e in event_log if e.get("type") == "agent_message_chunk"]
        if chunks:
            last_chunk = chunks[-1].get("text", "")
            print(f"\n  Agent output (last chunk, {len(last_chunk)} chars):")
            print("  " + last_chunk[:500].replace("\n", "\n  "))

        # Mark story as done if session succeeded
        if session.status == SessionStatus.COMPLETED:
            issue.state = done_state
            issue.completed_at = timezone.now()
            issue.save(update_fields=["state", "completed_at", "updated_at"])
            print(f"\n  ✓ Story {story_num} marked as DONE")
        else:
            print(f"\n  ✗ Story {story_num} did NOT complete successfully (status={session.status})")
            # Show relay error if any
            errors = [e for e in event_log if e.get("type") in ("relay_error", "relay_exit")]
            for err in errors:
                print(f"    Error event: {err}")

        results.append({
            "story_num": story_num,
            "story": issue.name[:60],
            "agent": agent_label,
            "status": session.status,
            "duration_s": elapsed,
            "tokens": tokens,
            "cost_usd": cost,
            "session_id": str(session.id),
        })

    except Exception as exc:
        elapsed = time.time() - t0
        print(f"\n  ✗ Exception dispatching Story {story_num}: {exc}")
        traceback.print_exc()
        results.append({
            "story_num": story_num,
            "story": issue.name[:60],
            "agent": agent_label,
            "status": "exception",
            "duration_s": elapsed,
            "error": str(exc),
        })

    # Brief pause between stories
    if story_num < len(created_stories):
        print(f"\n  Waiting 3s before next story...")
        time.sleep(3)


# ─────────────────────────────────────────────
# Phase 6: Sprint summary
# ─────────────────────────────────────────────
sep("PHASE 6 — Sprint Summary")

total_tokens = sum(r.get("tokens", 0) for r in results)
total_cost   = sum(r.get("cost_usd", 0) for r in results)
total_time   = sum(r.get("duration_s", 0) for r in results)
passed       = sum(1 for r in results if r.get("status") == SessionStatus.COMPLETED)

print(f"\n  Sprint: {SPRINT_NAME}")
print(f"  Project: {project.name}  ({project.id})")
print(f"\n  {'#':<3} {'Story':<52} {'Agent':<12} {'Status':<12} {'Tokens':>7} {'Cost':>8}")
print(f"  {'-'*3} {'-'*52} {'-'*12} {'-'*12} {'-'*7} {'-'*8}")
for r in results:
    status_display = str(r.get("status", "?"))[:10]
    tokens_display = str(r.get("tokens", 0))
    cost_display = f"${r.get('cost_usd', 0):.4f}"
    print(f"  {r['story_num']:<3} {r['story']:<52} {r['agent']:<12} {status_display:<12} {tokens_display:>7} {cost_display:>8}")

print(f"\n  Totals — tokens: {total_tokens}  cost: ${total_cost:.4f}  time: {total_time:.1f}s")
print(f"  Stories passed: {passed}/{len(results)}")

# Final issue states
print(f"\n  Final story states:")
for story_data in created_stories:
    issue = story_data["issue"]
    issue.refresh_from_db()
    state_name = issue.state.name if issue.state else "unknown"
    print(f"    [{story_data['agent_label']}] {issue.name[:50]} → {state_name}")

if passed == len(results):
    print(f"\n  ✓ ALL {len(results)} STORIES COMPLETED SUCCESSFULLY — Sprint PASSED!")
else:
    print(f"\n  ✗ Sprint had failures: {len(results)-passed}/{len(results)} stories did not complete")

print()
