from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from plane.app.agents.dispatcher import ACPXDispatcher
from plane.app.orchestrator.tools import _ensure_agent, _pick_dispatch_issue, _resolve_context
from plane.db.models import Agent

logger = logging.getLogger(__name__)


def _dispatch_cyrus_loop(*, workspace_id: str, headline: str, instructions: str) -> dict[str, Any]:
    ctx = _resolve_context({"workspace_id": workspace_id, "is_cyrus_agent": True})
    agent = _ensure_agent(ctx)
    work_item = _pick_dispatch_issue(ctx, {})
    prompt = "\n\n".join(
        [
            headline,
            instructions,
            "Mandatory operating rules:",
            "- Use `python manage.py cyrus_tool ...` for backend reads and writes.",
            "- Prefer autonomous delegation and backlog hygiene over escalation.",
            "- Register artifacts, outcomes, and approval needs explicitly.",
        ]
    )
    session = ACPXDispatcher(
        agent=agent,
        pool=agent.pool,
        project=work_item.project,
        work_item=work_item,
        goal=work_item.project.goal,
    ).dispatch(prompt)
    return {"session_id": str(session.id), "status": session.status, "headline": headline}


def _run_loop(workspace_id: str, headline: str, instructions: str) -> dict[str, Any]:
    if workspace_id:
        return _dispatch_cyrus_loop(workspace_id=workspace_id, headline=headline, instructions=instructions)
    results = []
    for agent in Agent.objects.filter(is_cyrus_agent=True, deleted_at__isnull=True).select_related("workspace"):
        results.append(_dispatch_cyrus_loop(workspace_id=str(agent.workspace_id), headline=headline, instructions=instructions))
    return {"headline": headline, "dispatches": results, "count": len(results)}


@shared_task
def visionary_ideation_loop(workspace_id: str) -> dict[str, Any]:
    return _run_loop(
        workspace_id=workspace_id,
        headline="Visionary ideation loop",
        instructions=(
            "Inspect open goals and recent outcomes. Use `get_activity_data_for_summary`, then create research spikes or "
            "new implementation stories with `create_work_item` when promising opportunities appear."
        ),
    )


@shared_task
def backlog_grooming_loop(workspace_id: str) -> dict[str, Any]:
    return _run_loop(
        workspace_id=workspace_id,
        headline="Backlog grooming loop",
        instructions=(
            "Gather recent activity, trace downstream pending work, enrich descriptions with new execution context, and prune "
            "invalid blockers or stale dependencies using `update_work_item`."
        ),
    )


@shared_task
def janitor_triage_loop(workspace_id: str) -> dict[str, Any]:
    return _run_loop(
        workspace_id=workspace_id,
        headline="Janitor triage loop",
        instructions=(
            "Audit running sessions older than 12 hours with no useful activity, mark failed stories, inspect artifacts for dead links, "
            "and estimate or tag raw intake tickets."
        ),
    )


@shared_task
def audit_alignment_loop(workspace_id: str) -> dict[str, Any]:
    return _run_loop(
        workspace_id=workspace_id,
        headline="Alignment audit loop",
        instructions=(
            "Spot-check KPI health with `ask_agent_question`, compare this week's work against active goal descriptions, and call "
            "`flag_alignment_drift` when execution has materially skewed."
        ),
    )
