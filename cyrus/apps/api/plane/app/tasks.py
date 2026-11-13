"""Celery task discovery shim for plane.app."""

from plane.app.agents.tasks import check_agent_health
from plane.app.orchestrator.loop_tasks import (
    audit_alignment_loop,
    backlog_grooming_loop,
    janitor_triage_loop,
    visionary_ideation_loop,
)
from plane.app.schedules.tasks import (
    detect_conflicts,
    execute_dispatch,
    manage_cycles,
    post_dispatch_analysis,
    scheduling_tick,
)
from plane.app.sessions.tasks import meter_session, summarize_session, trace_session_to_langfuse
from plane.app.wiki_sync.tasks import archivist_wiki_loop

__all__ = [
    "check_agent_health",
    "visionary_ideation_loop",
    "backlog_grooming_loop",
    "janitor_triage_loop",
    "audit_alignment_loop",
    "archivist_wiki_loop",
    "scheduling_tick",
    "execute_dispatch",
    "detect_conflicts",
    "manage_cycles",
    "post_dispatch_analysis",
    "meter_session",
    "summarize_session",
    "trace_session_to_langfuse",
]
