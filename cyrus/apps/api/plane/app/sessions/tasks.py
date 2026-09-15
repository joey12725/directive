from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def summarize_session(session_id):
    """
    Extract a summary from the session event log and persist it.

    If the session is linked to a work item, posts the summary as
    a comment so the story has a visible record of what was done.
    """
    from plane.db.models import CyrusSession
    from plane.app.orchestrator.lifecycle import _upsert_comment

    session = (
        CyrusSession.objects.select_related("work_item", "project", "agent")
        .filter(id=session_id)
        .first()
    )
    if session is None:
        logger.warning("summarize_session: session %s not found", session_id)
        return str(session_id)

    # If there's already a summary (e.g. from record_session_outcome), skip extraction
    if session.summary:
        _ensure_work_item_comment(session)
        return str(session_id)

    # Extract summary from event log
    summary = _extract_summary_from_events(session)
    if summary:
        session.summary = summary
        session.save(update_fields=["summary", "updated_at"])
        _ensure_work_item_comment(session)
        logger.info("summarize_session: saved summary for session %s (%d chars)", session_id, len(summary))
    else:
        logger.warning("summarize_session: could not extract summary for session %s", session_id)

    return str(session_id)


def _extract_summary_from_events(session) -> str | None:
    """
    Build a human-readable summary from the session's event_log.

    Strategies (in priority order):
    1. Look for an explicit summary/result event from the relay
    2. Collect agent_message_chunk events (the agent's final output)
    3. Summarise the list of tool calls made
    """
    events = session.event_log or []
    if not events:
        return None

    # Strategy 1: explicit summary event
    for event in reversed(events):
        if event.get("type") in ("summary", "result", "done"):
            text = event.get("summary") or event.get("text") or event.get("message")
            if text:
                return str(text).strip()

    # Strategy 2: agent message chunks (the agent's natural language output)
    message_chunks = [
        e.get("text", "")
        for e in events
        if e.get("type") == "agent_message_chunk" and e.get("text")
    ]
    if message_chunks:
        full_text = "".join(message_chunks).strip()
        # Take the last ~2000 chars as the most relevant output
        if len(full_text) > 2000:
            full_text = "..." + full_text[-2000:]
        return full_text

    # Strategy 3: list of tool calls as an activity log
    tool_calls = [
        e for e in events
        if e.get("type") in ("tool_use", "tool_call", "function_call")
    ]
    if tool_calls:
        lines = [f"Session performed {len(tool_calls)} operations:"]
        for tc in tool_calls[:20]:  # Cap at 20 entries
            name = tc.get("name") or tc.get("tool") or tc.get("function", {}).get("name", "unknown")
            lines.append(f"- {name}")
        if len(tool_calls) > 20:
            lines.append(f"- ... and {len(tool_calls) - 20} more")
        return "\n".join(lines)

    return None


def _ensure_work_item_comment(session) -> None:
    """Post the session summary as a comment on the linked work item, if not already done."""
    from plane.db.models import IssueComment
    from plane.app.orchestrator.lifecycle import _upsert_comment

    if not session.work_item_id or not session.summary:
        return

    # Check if a comment already exists for this session's summary
    # (avoid duplicates from both record_session_outcome and summarize_session)
    existing = IssueComment.objects.filter(
        issue=session.work_item,
        comment_html__contains=session.summary[:100],
    ).exists()

    if existing:
        return

    actor = None
    if session.project_id:
        try:
            actor = session.project.workspace.owner
        except Exception:
            pass

    agent_name = session.agent.name if session.agent_id else "Unknown agent"
    comment_body = (
        f"**Session summary** ({agent_name})\n\n"
        f"{session.summary}"
    )
    _upsert_comment(session.work_item, comment_body, actor)
    logger.info(
        "summarize_session: posted comment on work item %s for session %s",
        session.work_item_id,
        session.id,
    )


@shared_task
def trace_session_to_langfuse(session_id):
    """Placeholder for async Langfuse tracing."""

    return str(session_id)


@shared_task
def meter_session(session_id):
    """Placeholder for async session metering."""

    return str(session_id)
